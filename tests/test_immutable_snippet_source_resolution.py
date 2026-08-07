from __future__ import annotations

import pytest

from scripts.snippets.model import ImmutableSourceReference
from scripts.snippets.resolution import (
    SourceResolutionError,
    resolve_immutable_source,
)

COMMIT = "2c941ea9e834d7602d388f3271c0f864025ea756"


class FakeGitHub:
    def __init__(self, content: bytes = b"hello\n") -> None:
        self.content = content
        self.calls: list[tuple[str, str, str]] = []

    def read_file(self, repository: str, commit: str, path: str) -> bytes:
        self.calls.append((repository, commit, path))
        return self.content


def reference() -> ImmutableSourceReference:
    return ImmutableSourceReference(
        repository="canton-network/splice",
        commit=COMMIT,
        path="apps/example.yaml",
    )


def test_reads_the_exact_declared_commit() -> None:
    github = FakeGitHub()

    resolved = resolve_immutable_source(reference(), github)

    assert resolved.commit == COMMIT
    assert resolved.content == b"hello\n"
    assert github.calls == [
        ("canton-network/splice", COMMIT, "apps/example.yaml")
    ]


def test_rejects_source_larger_than_the_configured_limit() -> None:
    with pytest.raises(SourceResolutionError, match="4-byte size limit"):
        resolve_immutable_source(reference(), FakeGitHub(b"12345"), max_source_bytes=4)
