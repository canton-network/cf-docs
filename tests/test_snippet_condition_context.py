from __future__ import annotations

from scripts.snippets.model import IfVersionCondition, IfVersionTag
from scripts.snippets.references import parse_github_repository_url
from scripts.snippets.semantics import map_snippet_condition_contexts
from scripts.snippets.syntax import (
    parse_if_version_tags,
    parse_snippet_tags,
)


def conditions(text: str) -> tuple[IfVersionCondition, ...]:
    result: list[IfVersionCondition] = []
    for tag in parse_if_version_tags(text):
        if not isinstance(tag, IfVersionTag) or tag.closing:
            continue
        repository_value = tag.attribute("repository")
        candidate = tag.attribute("containsPullRequest")
        assert isinstance(repository_value, str)
        repository = parse_github_repository_url(repository_value)
        assert repository is not None
        assert isinstance(candidate, int)
        result.append(
            IfVersionCondition(
                repository=repository,
                contains_pull_request=candidate,
                span=tag.span,
            )
        )
    return tuple(result)


def contexts(text: str):
    return map_snippet_condition_contexts(
        parse_snippet_tags(text),
        parse_if_version_tags(text),
        conditions(text),
    )


def test_maps_unconditional_snippet_to_no_condition() -> None:
    result = contexts('<Snippet source="ref" language="yaml" />')

    assert len(result) == 1
    assert result[0].condition is None


def test_maps_both_branches_to_enclosing_condition() -> None:
    result = contexts(
        """<IfVersion repository="https://github.com/example/outer" containsPullRequest={12}>
<Snippet source="new" language="yaml" />
<Else>
<Snippet source="old" language="yaml" />
</Else>
</IfVersion>"""
    )

    assert [context.condition.contains_pull_request for context in result] == [
        12,
        12,
    ]


def test_maps_nested_snippet_to_innermost_condition() -> None:
    result = contexts(
        """<IfVersion repository="https://github.com/example/outer" containsPullRequest={12}>
<IfVersion repository="https://github.com/example/inner" containsPullRequest={34}>
<Snippet source="nested" language="yaml" />
</IfVersion>
</IfVersion>"""
    )

    assert result[0].condition is not None
    assert result[0].condition.repository == "example/inner"
    assert result[0].condition.contains_pull_request == 34
