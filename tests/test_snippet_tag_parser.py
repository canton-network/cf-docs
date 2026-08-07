from __future__ import annotations

import pytest

from scripts.snippets.syntax import DirectiveSyntaxError, parse_snippet_tags


def test_parses_multiline_snippet_attributes_without_interpreting_them() -> None:
    text = """Intro

  <Snippet
    source="https://github.com/example/repo/blob/abc/path.yaml"
    startAfter='START'
    language="yaml"
  />
"""

    snippets = parse_snippet_tags(text)

    assert len(snippets) == 1
    snippet = snippets[0]
    assert snippet.attribute("source") == (
        "https://github.com/example/repo/blob/abc/path.yaml"
    )
    assert snippet.attribute("startAfter") == "START"
    assert snippet.attribute("language") == "yaml"
    assert snippet.span.line == 3
    assert snippet.span.column == 3


def test_ignores_snippet_examples_in_code_and_comments() -> None:
    text = """````mdx
<Snippet source="fenced" />
````
{/* <Snippet source="commented" /> */}
`<Snippet source="inline" />`
"""

    assert parse_snippet_tags(text) == ()


@pytest.mark.parametrize(
    "text",
    [
        '<Snippet source="one" source="two" />',
        '<Snippet source="one" language />',
        '<Snippet source="one">',
        "</Snippet>",
    ],
)
def test_rejects_malformed_snippet_syntax(text: str) -> None:
    with pytest.raises(DirectiveSyntaxError):
        parse_snippet_tags(text)
