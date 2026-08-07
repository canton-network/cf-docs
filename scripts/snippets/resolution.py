from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model import ImmutableSourceReference

DEFAULT_MAX_SOURCE_BYTES = 1024 * 1024


class SourceResolutionError(Exception):
    """A snippet source could not be resolved safely."""


@dataclass(frozen=True)
class ResolvedSource:
    reference: ImmutableSourceReference
    commit: str
    content: bytes


class GitHubFileClient(Protocol):
    def read_file(self, repository: str, commit: str, path: str) -> bytes: ...


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
