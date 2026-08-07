from __future__ import annotations

from pathlib import PurePosixPath

from .registry import RepositoryRegistry


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
