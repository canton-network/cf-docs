from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .model import SnippetDirective, SourceKind, SourceReference


DEFAULT_MAX_SOURCE_BYTES = 1024 * 1024
REMOTE_PATTERNS = (
    re.compile(r"https://github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?$"),
    re.compile(r"git@github\.com:(?P<repo>[^/]+/[^/]+?)(?:\.git)?$"),
    re.compile(r"ssh://git@github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?$"),
)


class SourceResolutionError(Exception):
    pass


@dataclass(frozen=True)
class PullRequestResolution:
    head_commit: str
    merged: bool
    merge_commit: str | None


@dataclass(frozen=True)
class ResolvedSource:
    reference: SourceReference
    commit: str | None
    content: bytes


class GitHubSourceClient(Protocol):
    def resolve_pull_request(
        self, repository: str, pull_request: int
    ) -> PullRequestResolution: ...

    def read_file(self, repository: str, commit: str, path: str) -> bytes: ...


class GitHubClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
    ) -> None:
        self.token = (
            token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        )
        self.max_source_bytes = max_source_bytes

    def _request(
        self, url: str, *, accept: str, allow_not_found: bool = False
    ) -> bytes | None:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": accept,
                "User-Agent": "cf-docs-inline-snippets",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read(self.max_source_bytes + 1)
        except urllib.error.HTTPError as error:
            if error.code == 404 and allow_not_found:
                return None
            raise SourceResolutionError(
                f"GitHub returned HTTP {error.code} for {url}"
            ) from error
        except urllib.error.URLError as error:
            raise SourceResolutionError(
                f"Cannot fetch {url}: {error.reason}"
            ) from error
        if len(content) > self.max_source_bytes:
            raise SourceResolutionError(
                f"Source exceeds the {self.max_source_bytes}-byte size limit"
            )
        return content

    def _json(
        self, url: str, *, allow_not_found: bool = False
    ) -> dict[str, Any] | None:
        content = self._request(
            url,
            accept="application/vnd.github+json",
            allow_not_found=allow_not_found,
        )
        if content is None:
            return None
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise SourceResolutionError(
                f"GitHub returned invalid JSON for {url}"
            ) from error
        if not isinstance(payload, dict):
            raise SourceResolutionError(
                f"GitHub returned an unexpected response for {url}"
            )
        return payload

    def _json_list(self, url: str) -> list[dict[str, Any]]:
        content = self._request(url, accept="application/vnd.github+json")
        assert content is not None
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise SourceResolutionError(
                f"GitHub returned invalid JSON for {url}"
            ) from error
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            raise SourceResolutionError(
                f"GitHub returned an unexpected response for {url}"
            )
        return payload

    def resolve_pull_request(
        self, repository: str, pull_request: int
    ) -> PullRequestResolution:
        payload = self._json(
            f"https://api.github.com/repos/{repository}/pulls/{pull_request}"
        )
        assert payload is not None
        try:
            head_commit = payload["head"]["sha"]
        except (KeyError, TypeError) as error:
            raise SourceResolutionError(
                f"GitHub response for {repository}#{pull_request} has no head commit"
            ) from error
        merged = bool(payload.get("merged"))
        merge_commit = payload.get("merge_commit_sha") if merged else None
        if not isinstance(head_commit, str) or not re.fullmatch(
            r"[0-9a-fA-F]{40}", head_commit
        ):
            raise SourceResolutionError(
                f"GitHub returned an invalid head commit for {repository}#{pull_request}"
            )
        if merge_commit is not None and (
            not isinstance(merge_commit, str)
            or not re.fullmatch(r"[0-9a-fA-F]{40}", merge_commit)
        ):
            raise SourceResolutionError(
                f"GitHub returned an invalid merge commit for {repository}#{pull_request}"
            )
        return PullRequestResolution(
            head_commit.lower(), merged, merge_commit.lower() if merge_commit else None
        )

    def read_file(self, repository: str, commit: str, path: str) -> bytes:
        encoded_path = urllib.parse.quote(path, safe="/")
        encoded_ref = urllib.parse.quote(commit, safe="")
        content = self._request(
            f"https://api.github.com/repos/{repository}/contents/{encoded_path}?ref={encoded_ref}",
            accept="application/vnd.github.raw+json",
        )
        assert content is not None
        return content

    def resolve_commit(self, repository: str, ref: str) -> str:
        encoded_ref = urllib.parse.quote(ref, safe="")
        payload = self._json(
            f"https://api.github.com/repos/{repository}/commits/{encoded_ref}"
        )
        assert payload is not None
        commit = payload.get("sha")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
            raise SourceResolutionError(
                f"GitHub returned an invalid commit for {repository}@{ref}"
            )
        return commit.lower()

    def release_exists(self, repository: str, tag: str) -> bool:
        encoded_tag = urllib.parse.quote(tag, safe="")
        return (
            self._json(
                f"https://api.github.com/repos/{repository}/releases/tags/{encoded_tag}",
                allow_not_found=True,
            )
            is not None
        )

    def is_ancestor(self, repository: str, ancestor: str, descendant: str) -> bool:
        payload = self._json(
            f"https://api.github.com/repos/{repository}/compare/{ancestor}...{descendant}"
        )
        assert payload is not None
        status = payload.get("status")
        if status not in {"ahead", "behind", "diverged", "identical"}:
            raise SourceResolutionError(
                f"GitHub returned an invalid comparison for {repository}: {ancestor}...{descendant}"
            )
        return status in {"ahead", "identical"}

    def list_release_tags(self, repository: str) -> list[str]:
        tags: list[str] = []
        for page in range(1, 101):
            payload = self._json_list(
                f"https://api.github.com/repos/{repository}/releases?per_page=100&page={page}"
            )
            for release in payload:
                tag = release.get("tag_name")
                if isinstance(tag, str) and not release.get("draft"):
                    tags.append(tag)
            if len(payload) < 100:
                return tags
        raise SourceResolutionError(
            f"Refusing to paginate more than 10,000 releases for {repository}"
        )

    def list_tags(self, repository: str) -> list[str]:
        tags: list[str] = []
        for page in range(1, 101):
            payload = self._json_list(
                f"https://api.github.com/repos/{repository}/tags?per_page=100&page={page}"
            )
            for tag_data in payload:
                tag = tag_data.get("name")
                if isinstance(tag, str):
                    tags.append(tag)
            if len(payload) < 100:
                return tags
        raise SourceResolutionError(
            f"Refusing to paginate more than 10,000 tags for {repository}"
        )


def repository_from_remote(remote: str) -> str | None:
    for pattern in REMOTE_PATTERNS:
        match = pattern.fullmatch(remote.strip())
        if match:
            return match.group("repo")
    return None


class SourceResolver:
    def __init__(
        self,
        github: GitHubSourceClient,
        *,
        repositories: set[str],
        local_checkouts: dict[str, Path] | None = None,
        max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
        allow_local: bool = False,
    ) -> None:
        self.github = github
        self.repositories = repositories
        self.local_checkouts = local_checkouts or {}
        self.max_source_bytes = max_source_bytes
        self.allow_local = allow_local
        self._remote_cache: dict[tuple[str, str, str], bytes] = {}

    def resolve(
        self, reference: SourceReference, *, production: bool = False
    ) -> ResolvedSource:
        if reference.repository not in self.repositories:
            raise SourceResolutionError(
                f"Repository {reference.repository!r} is not allowlisted"
            )
        if reference.kind is SourceKind.IMMUTABLE:
            assert reference.commit is not None
            content = self._read_remote(
                reference.repository, reference.commit, reference.path
            )
            return self._bounded(reference, reference.commit, content)
        if reference.kind is SourceKind.PULL_REQUEST:
            assert reference.pull_request is not None
            pull_request = self.github.resolve_pull_request(
                reference.repository, reference.pull_request
            )
            if production:
                if not pull_request.merged or not pull_request.merge_commit:
                    raise SourceResolutionError(
                        f"{reference.repository}#{reference.pull_request} is not merged; candidate refs are preview-only"
                    )
                commit = pull_request.merge_commit
            else:
                commit = pull_request.head_commit
            content = self._read_remote(reference.repository, commit, reference.path)
            return self._bounded(reference, commit, content)
        if production and not self.allow_local:
            raise SourceResolutionError("Local snippet references are preview-only")
        return self._resolve_local(reference)

    def _read_remote(self, repository: str, commit: str, path: str) -> bytes:
        key = (repository, commit, path)
        if key not in self._remote_cache:
            self._remote_cache[key] = self.github.read_file(repository, commit, path)
        return self._remote_cache[key]

    def _bounded(
        self, reference: SourceReference, commit: str | None, content: bytes
    ) -> ResolvedSource:
        if len(content) > self.max_source_bytes:
            raise SourceResolutionError(
                f"Source exceeds the {self.max_source_bytes}-byte size limit"
            )
        return ResolvedSource(reference, commit, content)

    def _resolve_local(self, reference: SourceReference) -> ResolvedSource:
        checkout = self.local_checkouts.get(reference.repository)
        if checkout is None:
            raise SourceResolutionError(
                f"No local checkout was supplied for {reference.repository}"
            )
        root = checkout.expanduser().resolve()
        try:
            remote = subprocess.run(
                ["git", "-C", str(root), "remote", "get-url", "origin"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as error:
            raise SourceResolutionError(
                f"Local source is not a git checkout: {root}"
            ) from error
        actual_repository = repository_from_remote(remote)
        if actual_repository != reference.repository:
            raise SourceResolutionError(
                f"Local checkout {root} is {actual_repository or remote!r}, not {reference.repository!r}"
            )
        target = (root / reference.path).resolve()
        if not target.is_relative_to(root):
            raise SourceResolutionError(
                f"Local source path escapes checkout {root}: {reference.path}"
            )
        try:
            content = target.read_bytes()
        except OSError as error:
            raise SourceResolutionError(
                f"Cannot read local source {target}: {error}"
            ) from error
        return self._bounded(reference, None, content)


def extract_snippet(directive: SnippetDirective, source: ResolvedSource) -> str:
    try:
        text = source.content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceResolutionError(
            f"Snippet source is not UTF-8: {directive.source.path}"
        ) from error
    if "\x00" in text:
        raise SourceResolutionError(
            f"Snippet source contains a NUL byte: {directive.source.path}"
        )
    if directive.line_start is not None:
        assert directive.line_end is not None
        lines = text.splitlines()
        if directive.line_end > len(lines):
            raise SourceResolutionError(
                f"Line range {directive.line_start}..{directive.line_end} exceeds "
                f"the {len(lines)} lines in {directive.source.path}"
            )
        selected = "\n".join(lines[directive.line_start - 1 : directive.line_end])
    elif directive.start_after is not None:
        assert directive.end_before is not None
        lines = text.splitlines(keepends=True)
        starts = [
            index for index, line in enumerate(lines) if directive.start_after in line
        ]
        ends = [
            index for index, line in enumerate(lines) if directive.end_before in line
        ]
        if len(starts) != 1 or len(ends) != 1:
            raise SourceResolutionError(
                f"Expected exactly one {directive.start_after!r} and one {directive.end_before!r} "
                f"in {directive.source.path}; found {len(starts)} and {len(ends)}"
            )
        if starts[0] >= ends[0]:
            raise SourceResolutionError(
                f"Marker {directive.start_after!r} must occur before {directive.end_before!r} "
                f"in {directive.source.path}"
            )
        selected = "".join(lines[starts[0] + 1 : ends[0]])
    else:
        selected = text

    if directive.normalization == "baseline":
        selected_lines = selected.split("\n")
        indents = [
            len(line) - len(line.lstrip())
            for line in selected_lines
            if line.strip()
        ]
        strip = min(indents, default=0)
        selected = "\n".join(
            "" if not line.strip() else line[strip:] for line in selected_lines
        )
    if directive.normalization is not None:
        selected = re.sub(r"^\s*\n+", "", selected)
        selected = re.sub(r"\n+\s*$", "", selected)
    if directive.replace_from is not None:
        assert directive.replace_with is not None
        selected = selected.replace(directive.replace_from, directive.replace_with)
    return selected
