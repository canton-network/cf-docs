from __future__ import annotations

from pathlib import Path

import pytest

from scripts.snippets.diagnostics import if_version_structure_diagnostics
from scripts.snippets.model import (
    ConditionStructureIssue,
    ConditionStructureRule,
    Span,
)

PATH = Path("docs-main/validator.source.mdx")
SPAN = Span(start=20, end=30, line=7, column=3)


@pytest.mark.parametrize(
    ("rule", "code"),
    [
        (ConditionStructureRule.UNEXPECTED_CLOSE, "SNIP012"),
        (ConditionStructureRule.ELSE_NOT_DIRECT_CHILD, "SNIP025"),
        (ConditionStructureRule.UNCLOSED_TAG, "SNIP026"),
        (ConditionStructureRule.MULTIPLE_ELSE, "SNIP029"),
        (ConditionStructureRule.ELSE_NOT_FINAL, "SNIP030"),
    ],
)
def test_maps_structure_rule_to_stable_code(
    rule: ConditionStructureRule, code: str
) -> None:
    diagnostics = if_version_structure_diagnostics(
        PATH,
        (ConditionStructureIssue(rule=rule, span=SPAN, message="failure"),),
    )

    assert diagnostics[0].code == code
    assert diagnostics[0].span == SPAN
