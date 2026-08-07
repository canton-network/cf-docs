from __future__ import annotations

from pathlib import Path

import pytest

from scripts.snippets.diagnostics import snippet_attribute_diagnostics
from scripts.snippets.model import (
    SnippetAttributeIssue,
    SnippetAttributeRule,
    Span,
)

PATH = Path("docs-main/validator.source.mdx")
SPAN = Span(start=20, end=30, line=7, column=3)


@pytest.mark.parametrize(
    ("rule", "code"),
    [
        (SnippetAttributeRule.UNKNOWN_ATTRIBUTE, "SNIP015"),
        (SnippetAttributeRule.INVALID_LANGUAGE, "SNIP016"),
        (SnippetAttributeRule.INVALID_MARKERS, "SNIP017"),
    ],
)
def test_maps_basic_attribute_rule_to_stable_code(
    rule: SnippetAttributeRule, code: str
) -> None:
    diagnostics = snippet_attribute_diagnostics(
        PATH,
        (SnippetAttributeIssue(rule=rule, span=SPAN, message="failure"),),
    )

    assert diagnostics[0].code == code
    assert diagnostics[0].span == SPAN
