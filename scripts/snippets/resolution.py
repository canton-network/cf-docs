from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model import ImmutableSourceReference, PullRequestSnippetSource

DEFAULT_MAX_SOURCE_BYTES = 1024 * 1024


class SourceResolutionError(Exception):
    """A snippet source could not be resolved safely."""


@dataclass(frozen=True)
class ResolvedSource:
    reference: ImmutableSourceReference | PullRequestSnippetSource
    commit: str
    content: bytes


class GitHubFileClient(Protocol):
    def read_file(self, repository: str, commit: str, path: str) -> bytes: ...


@dataclass(frozen=True)
class PullRequestResolution:
    head_commit: str
    merged: bool
    merge_commit: str | None


class GitHubPullRequestClient(GitHubFileClient, Protocol):
    def resolve_pull_request(
        self, repository: str, pull_request: int
    ) -> PullRequestResolution: ...


def resolve_immutable_source(
    reference: ImmutableSourceReference,
    github: GitHubFileClient,
    *,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> ResolvedSource:
    """Read an immutable source at the exact commit declared by the page."""

    content = github.read_file(reference.repository, reference.commit, reference.path)
    if len(content) > max_source_bytes:
        raise SourceResolutionError(
            f"Source exceeds the {max_source_bytes}-byte size limit"
        )
    return ResolvedSource(reference, reference.commit, content)


def resolve_candidate_preview(
    reference: PullRequestSnippetSource,
    github: GitHubPullRequestClient,
    *,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> ResolvedSource:
    """Read a candidate source at its pull request's current head commit."""

    pull_request = github.resolve_pull_request(
        reference.repository, reference.pull_request
    )
    content = github.read_file(
        reference.repository, pull_request.head_commit, reference.path
    )
    if len(content) > max_source_bytes:
        raise SourceResolutionError(
            f"Source exceeds the {max_source_bytes}-byte size limit"
        )
    return ResolvedSource(reference, pull_request.head_commit, content)


def resolve_merged_candidate(
    reference: PullRequestSnippetSource,
    github: GitHubPullRequestClient,
    *,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> ResolvedSource:
    """Read a candidate at GitHub's merge commit after the pull request merges."""

    pull_request = github.resolve_pull_request(
        reference.repository, reference.pull_request
    )
    if not pull_request.merged or pull_request.merge_commit is None:
        raise SourceResolutionError(
            f"{reference.repository}#{reference.pull_request} is not merged; "
            "candidate refs are preview-only"
        )
    content = github.read_file(
        reference.repository, pull_request.merge_commit, reference.path
    )
    if len(content) > max_source_bytes:
        raise SourceResolutionError(
            f"Source exceeds the {max_source_bytes}-byte size limit"
        )
    return ResolvedSource(reference, pull_request.merge_commit, content)
