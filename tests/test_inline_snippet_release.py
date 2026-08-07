from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.snippets.model import IfVersionDirective, Span
from scripts.snippets.release import (
    ReleaseEvaluator,
    ReleaseResolutionError,
    ReleaseTarget,
    Version,
    load_deployed_targets,
)
from scripts.snippets.source import PullRequestResolution

REPOSITORY = "canton-network/splice"
HEAD = "7a6b8d9012fe34ac56bd7890ef12ab34cd56ef78"
MERGE = "e3f10a2479bc56de8012fa34bc56de7890ab12cd"
RELEASE = "b4c20b3580cd67ef9012ab45cd67ef8901ab23cd"
CONDITION = IfVersionDirective(REPOSITORY, 6123, Span(0, 1, 1, 1))
REPOSITORIES = {
    REPOSITORY: {
        "url": f"https://github.com/{REPOSITORY}",
        "release": {
            "type": "github-ancestor-with-artifact-release",
            "sourceTag": "{version}",
            "artifactRepository": "digital-asset/decentralized-canton-sync",
            "artifactTag": "v{version}",
        },
    }
}


class FakeGitHub:
    def __init__(
        self,
        *,
        merged: bool = True,
        artifact_published: bool = True,
        ancestor: bool = True,
    ) -> None:
        self.pull_request = PullRequestResolution(
            HEAD, merged, MERGE if merged else None
        )
        self.artifact_published = artifact_published
        self.ancestor = ancestor
        self.pull_calls = 0

    def resolve_pull_request(
        self, repository: str, pull_request: int
    ) -> PullRequestResolution:
        self.pull_calls += 1
        assert (repository, pull_request) == (REPOSITORY, 6123)
        return self.pull_request

    def resolve_commit(self, repository: str, ref: str) -> str:
        assert (repository, ref) == (REPOSITORY, "0.7.3")
        return RELEASE

    def release_exists(self, repository: str, tag: str) -> bool:
        assert (repository, tag) == (
            "digital-asset/decentralized-canton-sync",
            "v0.7.3",
        )
        return self.artifact_published

    def is_ancestor(self, repository: str, ancestor: str, descendant: str) -> bool:
        assert (repository, ancestor, descendant) == (REPOSITORY, MERGE, RELEASE)
        return self.ancestor

    def list_tags(self, repository: str) -> list[str]:
        assert repository == REPOSITORY
        return ["0.6.13", "0.6.14", "0.7.0", "0.7.1-rc1", "0.8.0"]

    def list_release_tags(self, repository: str) -> list[str]:
        assert repository == "digital-asset/decentralized-canton-sync"
        return ["v0.6.13", "v0.6.14", "v0.7.0", "v0.8.0"]


def test_release_requires_ancestry_and_matching_public_artifact() -> None:
    evaluator = ReleaseEvaluator(FakeGitHub(), REPOSITORIES)

    evidence = evaluator.evaluate(CONDITION, ReleaseTarget.exact("0.7.3"))

    assert evidence.contains_change
    assert evidence.candidate_commit == MERGE
    assert evidence.release_commit == RELEASE
    assert evidence.source_tag == "0.7.3"
    assert evidence.artifact_tag == "v0.7.3"


@pytest.mark.parametrize(
    ("artifact_published", "ancestor", "reason"),
    [
        (False, True, "artifact release"),
        (True, False, "not an ancestor"),
    ],
)
def test_release_fails_closed_without_both_proofs(
    artifact_published: bool, ancestor: bool, reason: str
) -> None:
    evaluator = ReleaseEvaluator(
        FakeGitHub(artifact_published=artifact_published, ancestor=ancestor),
        REPOSITORIES,
    )

    evidence = evaluator.evaluate(CONDITION, ReleaseTarget.exact("0.7.3"))

    assert not evidence.contains_change
    assert reason in evidence.reason


def test_open_pull_request_is_old_for_release_but_new_for_inferred_candidate() -> None:
    github = FakeGitHub(merged=False)
    evaluator = ReleaseEvaluator(github, REPOSITORIES)

    released = evaluator.evaluate(CONDITION, ReleaseTarget.exact("0.7.3"))
    candidate = evaluator.evaluate(CONDITION, ReleaseTarget.candidate_preview())

    assert not released.contains_change
    assert candidate.contains_change
    assert candidate.candidate_commit == HEAD
    assert github.pull_calls == 1


def test_version_is_strict_and_orderable() -> None:
    assert Version.parse("0.7.3") < Version.parse("0.8.0")
    with pytest.raises(ReleaseResolutionError):
        Version.parse("v0.7.3")
    with pytest.raises(ReleaseResolutionError):
        Version.parse("0.7")


def test_loads_deployed_splice_targets_in_dev_test_main_order(tmp_path: Path) -> None:
    dashboard = tmp_path / "repo-version-config.json"
    dashboard.write_text(
        json.dumps(
            {
                "versions": {
                    "mainnet": {
                        "name": "MainNet",
                        "substitutions": {"version_literal": "0.6.13"},
                    },
                    "testnet": {
                        "name": "TestNet",
                        "substitutions": {"version_literal": "0.6.14"},
                    },
                    "devnet": {
                        "name": "DevNet",
                        "substitutions": {"version_literal": "0.7.0"},
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    targets = load_deployed_targets(dashboard, repository=REPOSITORY)

    assert [(target.label, str(target.version)) for target in targets] == [
        ("DevNet", "0.7.0"),
        ("TestNet", "0.6.14"),
        ("MainNet", "0.6.13"),
    ]


def test_expands_inclusive_range_to_jointly_published_releases() -> None:
    evaluator = ReleaseEvaluator(FakeGitHub(), REPOSITORIES)

    targets = evaluator.published_targets_between(
        REPOSITORY, Version.parse("0.6.14"), Version.parse("0.7.0")
    )

    assert [str(target.version) for target in targets] == ["0.6.14", "0.7.0"]


def test_rejects_deployed_lookup_for_unconfigured_repository(tmp_path: Path) -> None:
    with pytest.raises(ReleaseResolutionError, match="not defined"):
        load_deployed_targets(tmp_path / "missing", repository="digital-asset/daml")
