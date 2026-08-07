from __future__ import annotations

import pytest

from scripts.snippets.model import (
    ImmutableSourceReference,
    SnippetSourceSafetyIssue,
    SnippetSourceSafetyRule,
    Span,
)
from scripts.snippets.registry import (
    RepositoryConfig,
    RepositoryRegistry,
    RepositoryVisibility,
)
from scripts.snippets.validation import validate_snippet_source_safety

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
SPAN = Span(start=0, end=1, line=1, column=1)
COMMIT = "2c941ea9e834d7602d388f3271c0f864025ea756"


def validate(
    repository: str, path: str
) -> tuple[SnippetSourceSafetyIssue, ...]:
    return validate_snippet_source_safety(
        ImmutableSourceReference(
            repository=repository, commit=COMMIT, path=path
        ),
        span=SPAN,
        registry=REGISTRY,
    )


def test_accepts_allowlisted_repository_and_safe_path() -> None:
    assert validate("canton-network/splice", "apps/file.yaml") == ()


@pytest.mark.parametrize(
    ("repository", "path", "rule"),
    [
        (
            "unknown/repository",
            "apps/file.yaml",
            SnippetSourceSafetyRule.UNREGISTERED_REPOSITORY,
        ),
        (
            "canton-network/splice",
            "../secret",
            SnippetSourceSafetyRule.UNSAFE_PATH,
        ),
    ],
)
def test_rejects_unregistered_repository_or_unsafe_path(
    repository: str, path: str, rule: SnippetSourceSafetyRule
) -> None:
    assert rule in {issue.rule for issue in validate(repository, path)}
