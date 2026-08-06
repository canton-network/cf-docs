from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .model import IfVersionDirective
from .source import PullRequestResolution


VERSION_RE = re.compile(
    r"(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)\.(?P<patch>0|[1-9][0-9]*)"
)
DEPLOYED_ORDER = ("devnet", "testnet", "mainnet")


class ReleaseResolutionError(Exception):
    pass


class ReleaseGitHubClient(Protocol):
    def resolve_pull_request(
        self, repository: str, pull_request: int
    ) -> PullRequestResolution: ...

    def resolve_commit(self, repository: str, ref: str) -> str: ...

    def release_exists(self, repository: str, tag: str) -> bool: ...

    def is_ancestor(self, repository: str, ancestor: str, descendant: str) -> bool: ...

    def list_release_tags(self, repository: str) -> list[str]: ...

    def list_tags(self, repository: str) -> list[str]: ...


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> Version:
        match = VERSION_RE.fullmatch(value)
        if not match:
            raise ReleaseResolutionError(
                f"Release version must be stable X.Y.Z, got {value!r}"
            )
        return cls(*(int(match.group(name)) for name in ("major", "minor", "patch")))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ReleaseTarget:
    version: Version | None
    label: str
    candidate: bool = False

    @classmethod
    def exact(cls, version: str, *, label: str | None = None) -> ReleaseTarget:
        parsed = Version.parse(version)
        return cls(parsed, label or str(parsed))

    @classmethod
    def candidate_preview(cls) -> ReleaseTarget:
        return cls(None, "Candidate", candidate=True)


@dataclass(frozen=True)
class ReleaseEvidence:
    repository: str
    pull_request: int
    target: ReleaseTarget
    candidate_commit: str
    release_commit: str | None
    source_tag: str | None
    artifact_repository: str | None
    artifact_tag: str | None
    artifact_published: bool
    contains_change: bool
    reason: str


class ReleaseEvaluator:
    def __init__(
        self,
        github: ReleaseGitHubClient,
        repositories: dict[str, dict[str, Any]],
    ) -> None:
        self.github = github
        self.repositories = repositories
        self._pull_requests: dict[tuple[str, int], PullRequestResolution] = {}
        self._evidence: dict[tuple[str, int, ReleaseTarget], ReleaseEvidence] = {}

    def evaluate(
        self, condition: IfVersionDirective, target: ReleaseTarget
    ) -> ReleaseEvidence:
        key = (condition.repository, condition.contains_pull_request, target)
        if key in self._evidence:
            return self._evidence[key]
        pull_request = self._resolve_pull_request(condition)
        if target.candidate:
            evidence = ReleaseEvidence(
                repository=condition.repository,
                pull_request=condition.contains_pull_request,
                target=target,
                candidate_commit=pull_request.head_commit,
                release_commit=None,
                source_tag=None,
                artifact_repository=None,
                artifact_tag=None,
                artifact_published=False,
                contains_change=True,
                reason="candidate preview uses the pull request head declared in the page",
            )
            self._evidence[key] = evidence
            return evidence
        if target.version is None:
            raise ReleaseResolutionError(
                "Non-candidate target requires a release version"
            )
        if not pull_request.merged or not pull_request.merge_commit:
            evidence = ReleaseEvidence(
                repository=condition.repository,
                pull_request=condition.contains_pull_request,
                target=target,
                candidate_commit=pull_request.head_commit,
                release_commit=None,
                source_tag=None,
                artifact_repository=None,
                artifact_tag=None,
                artifact_published=False,
                contains_change=False,
                reason="pull request is not merged",
            )
            self._evidence[key] = evidence
            return evidence

        repository = self.repositories.get(condition.repository)
        if repository is None:
            raise ReleaseResolutionError(
                f"Repository {condition.repository!r} is not registered"
            )
        release = repository.get("release")
        if not isinstance(release, dict):
            raise ReleaseResolutionError(
                f"Repository {condition.repository!r} has no release resolver"
            )
        if release.get("type") != "github-ancestor-with-artifact-release":
            raise ReleaseResolutionError(
                f"Unsupported release resolver {release.get('type')!r} for {condition.repository}"
            )
        version = str(target.version)
        try:
            source_tag = str(release["sourceTag"]).format(version=version)
            artifact_repository = str(release["artifactRepository"])
            artifact_tag = str(release["artifactTag"]).format(version=version)
        except KeyError as error:
            raise ReleaseResolutionError(
                f"Incomplete release resolver for {condition.repository}: missing {error.args[0]}"
            ) from error
        release_commit = self.github.resolve_commit(condition.repository, source_tag)
        artifact_published = self.github.release_exists(
            artifact_repository, artifact_tag
        )
        ancestor = self.github.is_ancestor(
            condition.repository, pull_request.merge_commit, release_commit
        )
        contains_change = artifact_published and ancestor
        if not artifact_published:
            reason = f"matching public artifact release {artifact_repository}@{artifact_tag} is missing"
        elif not ancestor:
            reason = "pull request merge commit is not an ancestor of the source release commit"
        else:
            reason = "merge commit is in the source release and the matching artifact release is published"
        evidence = ReleaseEvidence(
            repository=condition.repository,
            pull_request=condition.contains_pull_request,
            target=target,
            candidate_commit=pull_request.merge_commit,
            release_commit=release_commit,
            source_tag=source_tag,
            artifact_repository=artifact_repository,
            artifact_tag=artifact_tag,
            artifact_published=artifact_published,
            contains_change=contains_change,
            reason=reason,
        )
        self._evidence[key] = evidence
        return evidence

    def contains(self, condition: IfVersionDirective, target: ReleaseTarget) -> bool:
        return self.evaluate(condition, target).contains_change

    @property
    def evidence(self) -> tuple[ReleaseEvidence, ...]:
        return tuple(self._evidence.values())

    def published_targets_between(
        self,
        repository_name: str,
        start: Version,
        end: Version,
    ) -> list[ReleaseTarget]:
        if end < start:
            raise ReleaseResolutionError(
                f"Release range start {start} is after end {end}"
            )
        repository = self.repositories.get(repository_name)
        release = repository.get("release") if repository else None
        if not isinstance(release, dict):
            raise ReleaseResolutionError(
                f"Repository {repository_name!r} has no release resolver"
            )
        try:
            source_template = str(release["sourceTag"])
            artifact_repository = str(release["artifactRepository"])
            artifact_template = str(release["artifactTag"])
        except KeyError as error:
            raise ReleaseResolutionError(
                f"Incomplete release resolver for {repository_name}: missing {error.args[0]}"
            ) from error
        source_versions = self._versions_from_tags(
            self.github.list_tags(repository_name), source_template
        )
        artifact_versions = self._versions_from_tags(
            self.github.list_release_tags(artifact_repository), artifact_template
        )
        versions = sorted(
            version
            for version in source_versions & artifact_versions
            if start <= version <= end
        )
        if not versions:
            raise ReleaseResolutionError(
                f"No jointly published {repository_name} releases in {start}..{end}"
            )
        return [ReleaseTarget(version, str(version)) for version in versions]

    @staticmethod
    def _versions_from_tags(tags: list[str], template: str) -> set[Version]:
        if template.count("{version}") != 1:
            raise ReleaseResolutionError(
                f"Release tag template must contain one {{version}}: {template!r}"
            )
        prefix, suffix = template.split("{version}")
        versions: set[Version] = set()
        for tag in tags:
            if not tag.startswith(prefix) or (suffix and not tag.endswith(suffix)):
                continue
            end = len(tag) - len(suffix) if suffix else len(tag)
            candidate = tag[len(prefix) : end]
            try:
                versions.add(Version.parse(candidate))
            except ReleaseResolutionError:
                continue
        return versions

    def _resolve_pull_request(
        self, condition: IfVersionDirective
    ) -> PullRequestResolution:
        key = (condition.repository, condition.contains_pull_request)
        if key not in self._pull_requests:
            self._pull_requests[key] = self.github.resolve_pull_request(*key)
        return self._pull_requests[key]


def load_deployed_targets(
    dashboard_path: Path,
    *,
    repository: str,
) -> list[ReleaseTarget]:
    if repository != "canton-network/splice":
        raise ReleaseResolutionError(
            f"Deployed-version mapping is not defined for {repository}"
        )
    try:
        payload = json.loads(dashboard_path.read_text(encoding="utf-8"))
        networks = payload["versions"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ReleaseResolutionError(
            f"Cannot read deployed versions from {dashboard_path}: {error}"
        ) from error
    targets: list[ReleaseTarget] = []
    for network in DEPLOYED_ORDER:
        try:
            data = networks[network]
            label = data["name"]
            substitutions = data["substitutions"]
            version = substitutions.get("version_literal") or substitutions["version"]
        except (KeyError, TypeError) as error:
            raise ReleaseResolutionError(
                f"Dashboard has no usable {network} Splice version"
            ) from error
        targets.append(ReleaseTarget.exact(str(version), label=str(label)))
    return targets
