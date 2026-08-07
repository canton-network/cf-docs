from __future__ import annotations

from pathlib import Path

import pytest

from scripts.snippets.diagnostics import snippet_source_safety_diagnostics
from scripts.snippets.model import (
    SnippetSourceSafetyIssue,
    SnippetSourceSafetyRule,
    Span,
)

PATH = Path("docs-main/validator.source.mdx")
SPAN = Span(start=20, end=30, line=7, column=3)


@pytest.mark.parametrize(
    ("rule", "code"),
    [
        (SnippetSourceSafetyRule.UNREGISTERED_REPOSITORY, "SNIP009"),
        (SnippetSourceSafetyRule.UNSAFE_PATH, "SNIP010"),
    ],
)
def test_maps_source_safety_rule_to_stable_code(
    rule: SnippetSourceSafetyRule, code: str
) -> None:
    diagnostics = snippet_source_safety_diagnostics(
        PATH,
        (
            SnippetSourceSafetyIssue(
                rule=rule, span=SPAN, message="failure"
            ),
        ),
    )

    assert diagnostics[0].code == code
    assert diagnostics[0].span == SPAN
