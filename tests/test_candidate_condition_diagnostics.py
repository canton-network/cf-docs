from __future__ import annotations

from pathlib import Path

import pytest

from scripts.snippets.diagnostics import candidate_condition_diagnostics
from scripts.snippets.model import (
    CandidateConditionIssue,
    CandidateConditionRule,
    Span,
)

PATH = Path("docs-main/validator.source.mdx")
SPAN = Span(start=20, end=30, line=7, column=3)


@pytest.mark.parametrize(
    ("rule", "code"),
    [
        (CandidateConditionRule.CONDITION_REQUIRED, "SNIP027"),
        (CandidateConditionRule.IDENTITY_MISMATCH, "SNIP028"),
    ],
)
def test_maps_candidate_condition_rule_to_stable_code(
    rule: CandidateConditionRule, code: str
) -> None:
    diagnostics = candidate_condition_diagnostics(
        PATH,
        (CandidateConditionIssue(rule=rule, span=SPAN, message="failure"),),
    )

    assert diagnostics[0].code == code
    assert diagnostics[0].span == SPAN
