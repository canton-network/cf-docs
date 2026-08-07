from __future__ import annotations

import pytest

from scripts.snippets.model import SnippetAttributeRule
from scripts.snippets.semantics import validate_snippet_basic_attributes
from scripts.snippets.syntax import parse_snippet_tags


def rules(text: str) -> set[SnippetAttributeRule]:
    tag = parse_snippet_tags(text)[0]
    return {issue.rule for issue in validate_snippet_basic_attributes(tag)}


def test_accepts_valid_basic_attributes() -> None:
    assert rules(
        '<Snippet source="ref" startAfter="START" endBefore="END" '
        'language="yaml" />'
    ) == set()


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        (
            '<Snippet source="ref" unexpected="value" language="yaml" />',
            SnippetAttributeRule.UNKNOWN_ATTRIBUTE,
        ),
        (
            '<Snippet source="ref" language="two words" />',
            SnippetAttributeRule.INVALID_LANGUAGE,
        ),
        (
            '<Snippet source="ref" startAfter="START" language="yaml" />',
            SnippetAttributeRule.INVALID_MARKERS,
        ),
    ],
)
def test_rejects_invalid_basic_attributes(
    text: str, rule: SnippetAttributeRule
) -> None:
    assert rule in rules(text)
