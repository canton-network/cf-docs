from __future__ import annotations

import pytest

from scripts.snippets.model import ElseTag, IfVersionTag
from scripts.snippets.syntax import DirectiveSyntaxError, parse_if_version_tags


def test_parses_if_version_else_and_closing_tags() -> None:
    text = """<IfVersion
  repository="https://github.com/canton-network/splice"
  containsPullRequest={6123}
>
  New instructions.
<Else>
  Existing instructions.
</Else>
</IfVersion>
"""

    tags = parse_if_version_tags(text)

    assert len(tags) == 4
    opening = tags[0]
    assert isinstance(opening, IfVersionTag)
    assert opening.closing is False
    assert opening.attribute("repository") == (
        "https://github.com/canton-network/splice"
    )
    assert opening.attribute("containsPullRequest") == 6123
    assert opening.span.line == 1
    assert tags[1].closing is False
    assert isinstance(tags[1], ElseTag)
    assert tags[2].closing is True
    assert isinstance(tags[2], ElseTag)
    assert tags[3].closing is True
    assert isinstance(tags[3], IfVersionTag)


def test_does_not_apply_structural_nesting_rules() -> None:
    tags = parse_if_version_tags("<Else>orphan</Else>")

    assert len(tags) == 2
    assert all(isinstance(tag, ElseTag) for tag in tags)


def test_ignores_condition_examples_in_code_and_comments() -> None:
    text = """```mdx
<IfVersion repository="example"><Else></Else></IfVersion>
```
{/* <Else>commented</Else> */}
`<IfVersion repository="inline">`
"""

    assert parse_if_version_tags(text) == ()


@pytest.mark.parametrize(
    "text",
    [
        '<IfVersion repository="one" repository="two">',
        '<IfVersion repository="one" />',
        "<Else reason=\"fallback\">",
        "<Else />",
        "</IfVersion unexpected>",
    ],
)
def test_rejects_malformed_conditional_tag_syntax(text: str) -> None:
    with pytest.raises(DirectiveSyntaxError):
        parse_if_version_tags(text)
