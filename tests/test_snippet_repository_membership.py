from __future__ import annotations

from scripts.snippets.registry import (
    RepositoryConfig,
    RepositoryRegistry,
    RepositoryVisibility,
)
from scripts.snippets.validation import is_registered_repository

REGISTRY = RepositoryRegistry(
    (
        RepositoryConfig(
            name="canton-network/splice",
            url="https://github.com/canton-network/splice",
            default_branch="main",
            visibility=RepositoryVisibility.PUBLIC,
        ),
    )
)


def test_accepts_exact_allowlisted_repository_identity() -> None:
    assert is_registered_repository("canton-network/splice", REGISTRY)


def test_rejects_unknown_or_noncanonical_repository_identity() -> None:
    assert not is_registered_repository("unknown/repository", REGISTRY)
    assert not is_registered_repository("CANTON-NETWORK/SPLICE", REGISTRY)
