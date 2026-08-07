from __future__ import annotations

import re
from pathlib import PurePosixPath

from .registry import RepositoryRegistry

SAFE_LANGUAGE_RE = re.compile(r"[A-Za-z0-9_+.-]+")


def is_safe_source_path(value: str) -> bool:
    """Return whether a repository-relative path cannot escape its source."""

    path = PurePosixPath(value)
    return (
        bool(path.parts)
        and not value.startswith(("/", "\\"))
        and "\\" not in value
        and ".." not in path.parts
    )


def is_registered_repository(
    repository: str, registry: RepositoryRegistry
) -> bool:
    """Return whether a source repository appears in the explicit allowlist."""

    return registry.get(repository) is not None


def is_safe_language(value: str | int | None) -> bool:
    """Return whether a language is a non-empty safe fence identifier."""

    return isinstance(value, str) and SAFE_LANGUAGE_RE.fullmatch(value) is not None


def has_valid_marker_pair(
    start_after: str | int | None, end_before: str | int | None
) -> bool:
    """Return whether marker extraction is absent or a valid complete pair."""

    if start_after is None and end_before is None:
        return True
    return (
        isinstance(start_after, str)
        and isinstance(end_before, str)
        and bool(start_after)
        and bool(end_before)
        and start_after != end_before
    )
