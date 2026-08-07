from __future__ import annotations

import pytest

from scripts.snippets.model import PullRequestSnippetSource
from scripts.snippets.resolution import (
    PullRequestResolution,
    SourceResolutionError,
    resolve_merged_candidate,
)

HEAD = "7a6b8d9012fe34ac56bd7890ef12ab34cd56ef78"
MERGE = "e3f10a2479bc56de8012fa34bc56de7890ab12cd"


class FakeGitHub:
    def __init__(self, *, merged: bool) -> None:
        self.merged = merged
        self.read_calls: list[tuple[str, str, str]] = []

    def resolve_pull_request(
        self, repository: str, pull_request: int
    ) -> PullRequestResolution:
        return PullRequestResolution(HEAD, self.merged, MERGE if self.merged else None)

    def read_file(self, repository: str, commit: str, path: str) -> bytes:
        self.read_calls.append((repository, commit, path))
        return b"merged\n"


def reference() -> PullRequestSnippetSource:
    return PullRequestSnippetSource(
        repository="canton-network/splice",
        pull_request=6123,
        path="apps/example.yaml",
    )


def test_reads_candidate_at_github_merge_commit() -> None:
    github = FakeGitHub(merged=True)

    resolved = resolve_merged_candidate(reference(), github)

    assert resolved.commit == MERGE
    assert resolved.content == b"merged\n"
    assert github.read_calls == [
        ("canton-network/splice", MERGE, "apps/example.yaml")
    ]


def test_rejects_open_candidate_outside_preview() -> None:
    github = FakeGitHub(merged=False)

    with pytest.raises(SourceResolutionError, match="not merged"):
        resolve_merged_candidate(reference(), github)

    assert github.read_calls == []
