from __future__ import annotations

from scripts.snippets.model import PullRequestSnippetSource
from scripts.snippets.resolution import PullRequestResolution, resolve_candidate_preview

HEAD = "7a6b8d9012fe34ac56bd7890ef12ab34cd56ef78"


class FakeGitHub:
    def __init__(self) -> None:
        self.read_calls: list[tuple[str, str, str]] = []

    def resolve_pull_request(
        self, repository: str, pull_request: int
    ) -> PullRequestResolution:
        assert (repository, pull_request) == ("canton-network/splice", 6123)
        return PullRequestResolution(HEAD, False, None)

    def read_file(self, repository: str, commit: str, path: str) -> bytes:
        self.read_calls.append((repository, commit, path))
        return b"candidate\n"


def test_reads_candidate_at_current_pull_request_head() -> None:
    github = FakeGitHub()
    reference = PullRequestSnippetSource(
        repository="canton-network/splice",
        pull_request=6123,
        path="apps/example.yaml",
    )

    resolved = resolve_candidate_preview(reference, github)

    assert resolved.commit == HEAD
    assert resolved.content == b"candidate\n"
    assert github.read_calls == [
        ("canton-network/splice", HEAD, "apps/example.yaml")
    ]
