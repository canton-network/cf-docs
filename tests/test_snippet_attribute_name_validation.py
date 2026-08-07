from __future__ import annotations

from scripts.snippets.syntax import parse_snippet_tags
from scripts.snippets.validation import unknown_snippet_attributes


def test_accepts_supported_snippet_attribute_names() -> None:
    tag = parse_snippet_tags(
        """<Snippet
  source="ref"
  path="file"
  startAfter="start"
  endBefore="end"
  lines="1..2"
  normalize="preserve"
  trim="true"
  stripTrailingWhitespace="true"
  replaceFrom="old"
  replaceWith="new"
  language="yaml"
/>"""
    )[0]

    assert unknown_snippet_attributes(tag) == ()


def test_returns_unknown_names_in_deterministic_order() -> None:
    tag = parse_snippet_tags(
        '<Snippet zeta="one" source="ref" alpha="two" />'
    )[0]

    assert unknown_snippet_attributes(tag) == ("alpha", "zeta")
