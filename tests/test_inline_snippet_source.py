from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.snippets.model import SnippetDirective, SourceKind, SourceReference, Span
from scripts.snippets.source import (
    PullRequestResolution,
    ResolvedSource,
    SourceResolutionError,
    SourceResolver,
    extract_snippet,
    repository_from_remote,
)


REPOSITORY = "canton-network/splice"
COMMIT = "2c941ea9e834d7602d388f3271c0f864025ea756"
HEAD = "7a6b8d9012fe34ac56bd7890ef12ab34cd56ef78"
MERGE = "e3f10a2479bc56de8012fa34bc56de7890ab12cd"


class FakeGitHub:
    def __init__(self, *, merged: bool = True, content: bytes = b"hello\n") -> None:
        self.pull_request = PullRequestResolution(
            HEAD, merged, MERGE if merged else None
        )
        self.content = content
        self.read_calls: list[tuple[str, str, str]] = []

    def resolve_pull_request(
        self, repository: str, pull_request: int
    ) -> PullRequestResolution:
        assert (repository, pull_request) == (REPOSITORY, 6123)
        return self.pull_request

    def read_file(self, repository: str, commit: str, path: str) -> bytes:
        self.read_calls.append((repository, commit, path))
        return self.content


def reference(kind: SourceKind, **kwargs) -> SourceReference:
    return SourceReference(kind, REPOSITORY, "apps/example.yaml", **kwargs)


def directive(
    *, start_after: str | None = None, end_before: str | None = None
) -> SnippetDirective:
    return SnippetDirective(
        source=reference(SourceKind.IMMUTABLE, commit=COMMIT),
        language="yaml",
        start_after=start_after,
        end_before=end_before,
        line_start=None,
        line_end=None,
        normalization=None,
        trim=False,
        replace_from=None,
        replace_with=None,
        span=Span(0, 1, 1, 1),
    )


def resolver(github: FakeGitHub, **kwargs) -> SourceResolver:
    return SourceResolver(github, repositories={REPOSITORY}, **kwargs)


def test_resolves_immutable_source_without_ref_lookup() -> None:
    github = FakeGitHub()

    resolved = resolver(github).resolve(
        reference(SourceKind.IMMUTABLE, commit=COMMIT), production=True
    )

    assert resolved.commit == COMMIT
    assert github.read_calls == [(REPOSITORY, COMMIT, "apps/example.yaml")]


def test_reuses_one_remote_read_for_repeated_immutable_source() -> None:
    github = FakeGitHub()
    source_resolver = resolver(github)
    immutable = reference(SourceKind.IMMUTABLE, commit=COMMIT)

    source_resolver.resolve(immutable, production=True)
    source_resolver.resolve(immutable, production=True)

    assert github.read_calls == [(REPOSITORY, COMMIT, "apps/example.yaml")]


def test_candidate_uses_head_for_preview_and_merge_commit_for_production() -> None:
    github = FakeGitHub()
    candidate = reference(SourceKind.PULL_REQUEST, pull_request=6123)
    source_resolver = resolver(github)

    assert source_resolver.resolve(candidate).commit == HEAD
    assert source_resolver.resolve(candidate, production=True).commit == MERGE
    assert github.read_calls == [
        (REPOSITORY, HEAD, "apps/example.yaml"),
        (REPOSITORY, MERGE, "apps/example.yaml"),
    ]


def test_open_candidate_is_rejected_for_production() -> None:
    source_resolver = resolver(FakeGitHub(merged=False))

    with pytest.raises(SourceResolutionError, match="not merged"):
        source_resolver.resolve(
            reference(SourceKind.PULL_REQUEST, pull_request=6123), production=True
        )


def test_local_source_requires_matching_git_remote(tmp_path: Path) -> None:
    checkout = tmp_path / "splice"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", checkout], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            checkout,
            "remote",
            "add",
            "origin",
            "git@github.com:canton-network/splice.git",
        ],
        check=True,
    )
    source = checkout / "apps" / "example.yaml"
    source.parent.mkdir()
    source.write_text("local\n", encoding="utf-8")

    resolved = resolver(
        FakeGitHub(), local_checkouts={REPOSITORY: checkout}, allow_local=True
    ).resolve(reference(SourceKind.LOCAL))

    assert resolved.content == b"local\n"
    assert resolved.commit is None


def test_local_source_rejects_checkout_identity_mismatch(tmp_path: Path) -> None:
    checkout = tmp_path / "other"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", checkout], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            checkout,
            "remote",
            "add",
            "origin",
            "https://github.com/example/other.git",
        ],
        check=True,
    )

    with pytest.raises(SourceResolutionError, match="not 'canton-network/splice'"):
        resolver(
            FakeGitHub(), local_checkouts={REPOSITORY: checkout}, allow_local=True
        ).resolve(reference(SourceKind.LOCAL))


def test_size_limit_applies_to_all_clients() -> None:
    with pytest.raises(SourceResolutionError, match="size limit"):
        SourceResolver(
            FakeGitHub(content=b"12345"),
            repositories={REPOSITORY},
            max_source_bytes=4,
        ).resolve(reference(SourceKind.IMMUTABLE, commit=COMMIT))


def test_extracts_content_strictly_between_unique_marker_lines() -> None:
    source = ResolvedSource(
        reference(SourceKind.IMMUTABLE, commit=COMMIT),
        COMMIT,
        b"before\n# SWEEP_START\nvalue: true\n# SWEEP_END\nafter\n",
    )

    assert (
        extract_snippet(
            directive(start_after="SWEEP_START", end_before="SWEEP_END"), source
        )
        == "value: true\n"
    )


def test_extracts_legacy_lines_with_baseline_normalization_and_replacement() -> None:
    source = ResolvedSource(
        reference(SourceKind.IMMUTABLE, commit=COMMIT),
        COMMIT,
        b"ignored\n    old: true\n      nested: true\nignored\n",
    )
    item = SnippetDirective(
        source=reference(SourceKind.IMMUTABLE, commit=COMMIT),
        language="yaml",
        start_after=None,
        end_before=None,
        line_start=2,
        line_end=3,
        normalization="baseline",
        trim=False,
        replace_from="old",
        replace_with="new",
        span=Span(0, 1, 1, 1),
    )

    assert extract_snippet(item, source) == "new: true\n  nested: true"

@pytest.mark.parametrize(
    "content",
    [
        b"SWEEP_START\none\nSWEEP_START\ntwo\nSWEEP_END\n",
        b"SWEEP_START\nvalue\n",
        b"SWEEP_END\nvalue\nSWEEP_START\n",
    ],
)
def test_rejects_ambiguous_or_reversed_markers(content: bytes) -> None:
    source = ResolvedSource(
        reference(SourceKind.IMMUTABLE, commit=COMMIT), COMMIT, content
    )

    with pytest.raises(SourceResolutionError):
        extract_snippet(
            directive(start_after="SWEEP_START", end_before="SWEEP_END"), source
        )


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("https://github.com/canton-network/splice.git", REPOSITORY),
        ("git@github.com:canton-network/splice.git", REPOSITORY),
        ("ssh://git@github.com/canton-network/splice", REPOSITORY),
        ("https://gitlab.com/canton-network/splice", None),
    ],
)
def test_normalizes_supported_github_remotes(remote: str, expected: str | None) -> None:
    assert repository_from_remote(remote) == expected
