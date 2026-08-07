from __future__ import annotations

from collections.abc import Callable

import pytest

from scripts.snippets.model import DirectiveSyntaxRule
from scripts.snippets.syntax import (
    DirectiveSyntaxError,
    parse_if_version_tags,
    parse_snippet_tags,
)


@pytest.mark.parametrize(
    ("parser", "text", "rule"),
    [
        (
            parse_snippet_tags,
            '<Snippet source="one" language />',
            DirectiveSyntaxRule.MALFORMED_ATTRIBUTES,
        ),
        (
            parse_snippet_tags,
            '<Snippet source="one" source="two" />',
            DirectiveSyntaxRule.DUPLICATE_ATTRIBUTE,
        ),
        (
            parse_snippet_tags,
            '<Snippet source="one">',
            DirectiveSyntaxRule.SNIPPET_NOT_SELF_CLOSING,
        ),
        (
            parse_if_version_tags,
            '<IfVersion repository="one" />',
            DirectiveSyntaxRule.IF_VERSION_SELF_CLOSING,
        ),
        (
            parse_if_version_tags,
            "<Else />",
            DirectiveSyntaxRule.ELSE_SELF_CLOSING,
        ),
        (
            parse_if_version_tags,
            "</IfVersion unexpected>",
            DirectiveSyntaxRule.CLOSING_ATTRIBUTES,
        ),
        (
            parse_if_version_tags,
            '<Else reason="fallback">',
            DirectiveSyntaxRule.ELSE_ATTRIBUTES,
        ),
    ],
)
def test_classifies_syntax_error(
    parser: Callable[[str], object], text: str, rule: DirectiveSyntaxRule
) -> None:
    with pytest.raises(DirectiveSyntaxError) as error:
        parser(text)

    assert error.value.rule is rule
