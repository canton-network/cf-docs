from __future__ import annotations

import pytest

from scripts.snippets.model import (
    ImmutableSourceReference,
    LocalSourceReference,
    PullRequestSnippetSource,
    SnippetSourceAttributeRule,
    SnippetSourceAttributeValidation,
)
from scripts.snippets.semantics import resolve_snippet_source_attributes
from scripts.snippets.syntax import parse_snippet_tags

COMMIT = "2c941ea9e834d7602d388f3271c0f864025ea756"


def resolve(text: str) -> SnippetSourceAttributeValidation:
    return resolve_snippet_source_attributes(parse_snippet_tags(text)[0])


@pytest.mark.parametrize(
    ("text", "source_type"),
    [
        (
            f'<Snippet source="https://github.com/example/repo/blob/{COMMIT}/file" />',
            ImmutableSourceReference,
        ),
        (
            (
                '<Snippet source="https://github.com/example/repo/pull/12" '
                'path="file" />'
            ),
            PullRequestSnippetSource,
        ),
        (
            '<Snippet source="local://example/repo/file" />',
            LocalSourceReference,
        ),
    ],
)
def test_resolves_supported_source_and_path_shapes(
    text: str, source_type: type[object]
) -> None:
    result = resolve(text)

    assert result.issues == ()
    assert isinstance(result.source, source_type)


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("<Snippet />", SnippetSourceAttributeRule.SOURCE_REQUIRED),
        ("<Snippet source={12} />", SnippetSourceAttributeRule.SOURCE_REQUIRED),
        (
            '<Snippet source="https://example.com/file" />',
            SnippetSourceAttributeRule.UNSUPPORTED_SOURCE,
        ),
        (
            '<Snippet source="https://github.com/example/repo/pull/12" path={3} />',
            SnippetSourceAttributeRule.PATH_MUST_BE_QUOTED,
        ),
        (
            (
                f'<Snippet source="https://github.com/example/repo/blob/{COMMIT}/file" '
                'path="other" />'
            ),
            SnippetSourceAttributeRule.IMMUTABLE_PATH_FORBIDDEN,
        ),
        (
            '<Snippet source="https://github.com/example/repo/pull/12" />',
            SnippetSourceAttributeRule.PULL_REQUEST_PATH_REQUIRED,
        ),
        (
            '<Snippet source="local://example/repo/file" path="other" />',
            SnippetSourceAttributeRule.LOCAL_PATH_FORBIDDEN,
        ),
    ],
)
def test_rejects_invalid_source_and_path_attribute_shapes(
    text: str, rule: SnippetSourceAttributeRule
) -> None:
    assert rule in {issue.rule for issue in resolve(text).issues}
