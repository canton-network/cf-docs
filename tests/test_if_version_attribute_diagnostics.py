from __future__ import annotations

from pathlib import Path

import pytest

from scripts.snippets.diagnostics import if_version_attribute_diagnostics
from scripts.snippets.model import (
    IfVersionAttributeIssue,
    IfVersionAttributeRule,
    Span,
)

PATH = Path("docs-main/validator.source.mdx")
SPAN = Span(start=20, end=30, line=7, column=3)


@pytest.mark.parametrize(
    ("rule", "code"),
    [
        (IfVersionAttributeRule.UNKNOWN_ATTRIBUTE, "SNIP020"),
        (IfVersionAttributeRule.INVALID_REPOSITORY, "SNIP021"),
        (IfVersionAttributeRule.UNREGISTERED_REPOSITORY, "SNIP022"),
        (IfVersionAttributeRule.INVALID_PULL_REQUEST, "SNIP023"),
    ],
)
def test_maps_if_version_attribute_rule_to_stable_code(
    rule: IfVersionAttributeRule, code: str
) -> None:
    diagnostics = if_version_attribute_diagnostics(
        PATH,
        (IfVersionAttributeIssue(rule=rule, span=SPAN, message="failure"),),
    )

    assert diagnostics[0].code == code
    assert diagnostics[0].span == SPAN
