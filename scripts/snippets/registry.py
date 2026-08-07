from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class RepositoryVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class RepositoryRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class RepositoryConfig:
    name: str
    url: str
    default_branch: str
    visibility: RepositoryVisibility


@dataclass(frozen=True)
class RepositoryRegistry:
    repositories: tuple[RepositoryConfig, ...]

    def get(self, name: str) -> RepositoryConfig | None:
        return next(
            (repository for repository in self.repositories if repository.name == name),
            None,
        )


def _required_string(entry: object, key: str, *, repository: str) -> str:
    if not isinstance(entry, dict):
        raise RepositoryRegistryError(
            f"Repository {repository!r} must be an object"
        )
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise RepositoryRegistryError(
            f"Repository {repository!r} requires a non-empty {key!r} string"
        )
    return value


def load_repository_registry(path: Path) -> RepositoryRegistry:
    """Load repository identity data from the checked-in registry."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RepositoryRegistryError(
            f"Cannot read snippet repository registry {path}: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise RepositoryRegistryError(
            f"Snippet repository registry {path} must be an object"
        )
    entries = payload.get("repositories")
    if not isinstance(entries, dict) or not entries:
        raise RepositoryRegistryError(
            f"Snippet repository registry {path} must contain repositories"
        )

    repositories: list[RepositoryConfig] = []
    for name in sorted(entries):
        if not isinstance(name, str) or not name:
            raise RepositoryRegistryError(
                "Repository names must be non-empty strings"
            )
        entry = entries[name]
        url = _required_string(entry, "url", repository=name)
        expected_url = f"https://github.com/{name}"
        if url != expected_url:
            raise RepositoryRegistryError(
                f"Repository {name!r} URL must be its canonical GitHub URL "
                f"{expected_url!r}"
            )
        default_branch = _required_string(
            entry, "defaultBranch", repository=name
        )
        visibility_value = _required_string(
            entry, "visibility", repository=name
        )
        try:
            visibility = RepositoryVisibility(visibility_value)
        except ValueError as error:
            raise RepositoryRegistryError(
                f"Repository {name!r} visibility must be 'public' or 'private'"
            ) from error
        repositories.append(
            RepositoryConfig(
                name=name,
                url=url,
                default_branch=default_branch,
                visibility=visibility,
            )
        )
    return RepositoryRegistry(tuple(repositories))
