from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.snippets.diagnostics import directive_syntax_diagnostic
from scripts.snippets.syntax import (
    DirectiveSyntaxError,
    parse_if_version_tags,
    parse_snippet_tags,
)

PATH = Path("docs-main/validator.source.mdx")


@pytest.mark.parametrize(
    ("parser", "text", "code"),
    [
        (parse_snippet_tags, '<Snippet source="one" language />', "SNIP013"),
        (
            parse_snippet_tags,
            '<Snippet source="one" source="two" />',
            "SNIP013",
        ),
        (parse_snippet_tags, '<Snippet source="one">', "SNIP014"),
        (
            parse_if_version_tags,
            '<IfVersion repository="one" />',
            "SNIP019",
        ),
        (parse_if_version_tags, "<Else />", "SNIP024"),
        (
            parse_if_version_tags,
            "</IfVersion unexpected>",
            "SNIP011",
        ),
        (
            parse_if_version_tags,
            '<Else reason="fallback">',
            "SNIP024",
        ),
    ],
)
def test_maps_syntax_rule_to_stable_code(
    parser: Callable[[str], object], text: str, code: str
) -> None:
    with pytest.raises(DirectiveSyntaxError) as error:
        parser(text)

    diagnostic = directive_syntax_diagnostic(PATH, error.value)
    assert diagnostic.code == code
    assert diagnostic.span == error.value.span
