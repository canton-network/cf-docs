from __future__ import annotations

from pathlib import Path

import pytest

from scripts.snippets.model import SnippetValidationError, SourceKind
from scripts.snippets.parser import parse_page


REPOSITORIES = {
    "canton-network/splice": {
        "url": "https://github.com/canton-network/splice",
        "defaultBranch": "main",
    }
}
PAGE = Path("docs-main/example.source.mdx")
COMMIT = "2c941ea9e834d7602d388f3271c0f864025ea756"


def parse(text: str, *, allow_local: bool = False):
    return parse_page(
        text, path=PAGE, repositories=REPOSITORIES, allow_local=allow_local
    )


def diagnostic_codes(text: str, *, allow_local: bool = False) -> set[str]:
    with pytest.raises(SnippetValidationError) as error:
        parse(text, allow_local=allow_local)
    return {diagnostic.code for diagnostic in error.value.diagnostics}


def test_parses_complete_immutable_reference() -> None:
    page = parse(
        f"""<Snippet
  source="https://github.com/canton-network/splice/blob/{COMMIT}/apps/validator-values.yaml"
  startAfter="SWEEP_START"
  endBefore="SWEEP_END"
  language="yaml"
/>"""
    )

    assert len(page.snippets) == 1
    snippet = page.snippets[0]
    assert snippet.source.kind is SourceKind.IMMUTABLE
    assert snippet.source.repository == "canton-network/splice"
    assert snippet.source.commit == COMMIT
    assert snippet.source.path == "apps/validator-values.yaml"


def test_parses_candidate_inside_release_condition() -> None:
    page = parse(
        """<IfVersion
  repository="https://github.com/canton-network/splice"
  containsPullRequest={6123}
>
  New prose.
  <Snippet
    source="https://github.com/canton-network/splice/pull/6123"
    path="apps/validator-values.yaml"
    language="yaml"
  />
<Else>
  Existing prose.
</Else>
</IfVersion>"""
    )

    assert page.conditions[0].contains_pull_request == 6123
    assert page.snippets[0].source.kind is SourceKind.PULL_REQUEST
    assert page.snippets[0].source.pull_request == 6123


def test_ignores_examples_in_fenced_code_and_comments() -> None:
    page = parse(
        """```mdx
<Snippet source="not-a-ref" />
```
{/* <IfVersion bogus> */}
"""
    )

    assert page.snippets == ()
    assert page.conditions == ()


def test_local_reference_is_preview_only() -> None:
    text = '<Snippet source="local://canton-network/splice/apps/example.yaml" language="yaml" />'

    assert "SNIP007" in diagnostic_codes(text)
    page = parse(text, allow_local=True)
    assert page.snippets[0].source.kind is SourceKind.LOCAL


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (
            '<Snippet source="https://github.com/canton-network/splice/blob/main/a.yaml" language="yaml" />',
            "SNIP008",
        ),
        (
            f'<Snippet source="https://github.com/unknown/repo/blob/{COMMIT}/a.yaml" language="yaml" />',
            "SNIP009",
        ),
        (
            f'<Snippet source="https://github.com/canton-network/splice/blob/{COMMIT}/../secret" language="yaml" />',
            "SNIP010",
        ),
        (
            f'<Snippet source="https://github.com/canton-network/splice/blob/{COMMIT}/a.yaml" startAfter="START" language="yaml" />',
            "SNIP017",
        ),
        (
            '<Snippet source="https://github.com/canton-network/splice/pull/6123" language="yaml" />',
            "SNIP005",
        ),
        (
            '<Snippet source="https://github.com/canton-network/splice/pull/6123" path="a.yaml" language="yaml" />',
            "SNIP027",
        ),
        (
            """<IfVersion repository="https://github.com/canton-network/splice" containsPullRequest={6123}>
<Snippet source="https://github.com/canton-network/splice/pull/6124" path="a.yaml" language="yaml" />
</IfVersion>""",
            "SNIP028",
        ),
        ("<Else>orphan</Else>", "SNIP025"),
    ],
)
def test_rejects_invalid_contract(text: str, code: str) -> None:
    assert code in diagnostic_codes(text)


def test_diagnostic_points_to_declaration_line() -> None:
    with pytest.raises(SnippetValidationError) as error:
        parse('\n\n<Snippet source="bad" language="yaml" />')

    diagnostic = next(
        item for item in error.value.diagnostics if item.code == "SNIP008"
    )
    assert diagnostic.line == 3
    assert diagnostic.column == 1
