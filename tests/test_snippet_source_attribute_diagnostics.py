from __future__ import annotations

from pathlib import Path

import pytest

from scripts.snippets.diagnostics import snippet_source_attribute_diagnostics
from scripts.snippets.model import (
    SnippetSourceAttributeIssue,
    SnippetSourceAttributeRule,
    Span,
)

PATH = Path("docs-main/validator.source.mdx")
SPAN = Span(start=20, end=30, line=7, column=3)


@pytest.mark.parametrize(
    ("rule", "code"),
    [
        (SnippetSourceAttributeRule.SOURCE_REQUIRED, "SNIP002"),
        (SnippetSourceAttributeRule.PATH_MUST_BE_QUOTED, "SNIP003"),
        (SnippetSourceAttributeRule.IMMUTABLE_PATH_FORBIDDEN, "SNIP004"),
        (SnippetSourceAttributeRule.PULL_REQUEST_PATH_REQUIRED, "SNIP005"),
        (SnippetSourceAttributeRule.LOCAL_PATH_FORBIDDEN, "SNIP006"),
        (SnippetSourceAttributeRule.UNSUPPORTED_SOURCE, "SNIP008"),
    ],
)
def test_maps_source_attribute_rule_to_stable_code(
    rule: SnippetSourceAttributeRule, code: str
) -> None:
    diagnostics = snippet_source_attribute_diagnostics(
        PATH,
        (
            SnippetSourceAttributeIssue(
                rule=rule, span=SPAN, message="failure"
            ),
        ),
    )

    assert diagnostics[0].code == code
    assert diagnostics[0].span == SPAN
