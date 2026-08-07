from __future__ import annotations

import pytest

from scripts.snippets.model import ConditionStructureRule
from scripts.snippets.syntax import parse_if_version_tags
from scripts.snippets.validation import validate_if_version_structure


def rules(text: str) -> list[ConditionStructureRule]:
    return [
        issue.rule
        for issue in validate_if_version_structure(
            text, parse_if_version_tags(text)
        )
    ]


def test_accepts_balanced_condition_with_optional_else() -> None:
    assert rules(
        """<IfVersion repository="one">
new
<Else>
old
</Else>
</IfVersion>"""
    ) == []


def test_accepts_nested_conditions_before_else() -> None:
    assert rules(
        """<IfVersion repository="outer">
<IfVersion repository="inner">inner</IfVersion>
<Else>old</Else>
</IfVersion>"""
    ) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<Else>orphan</Else>", ConditionStructureRule.ELSE_NOT_DIRECT_CHILD),
        (
            "<IfVersion><Else>one</Else><Else>two</Else></IfVersion>",
            ConditionStructureRule.MULTIPLE_ELSE,
        ),
        (
            "<IfVersion><Else>old</Else>new tail</IfVersion>",
            ConditionStructureRule.ELSE_NOT_FINAL,
        ),
        ("</IfVersion>", ConditionStructureRule.UNEXPECTED_CLOSE),
        ("<IfVersion>open", ConditionStructureRule.UNCLOSED_TAG),
        (
            "<IfVersion><Else>old</IfVersion>",
            ConditionStructureRule.UNEXPECTED_CLOSE,
        ),
    ],
)
def test_rejects_invalid_conditional_structure(
    text: str, expected: ConditionStructureRule
) -> None:
    assert expected in rules(text)
