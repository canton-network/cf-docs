from __future__ import annotations

from pathlib import Path

from scripts.snippets.page_validation import validate_authored_page
from scripts.snippets.registry import (
    RepositoryConfig,
    RepositoryRegistry,
    RepositoryVisibility,
)

PATH = Path("docs-main/validator.source.mdx")
REGISTRY = RepositoryRegistry(
    (
        RepositoryConfig(
            name="canton-network/splice",
            url="https://github.com/canton-network/splice",
            default_branch="main",
            visibility=RepositoryVisibility.PUBLIC,
        ),
    )
)


def test_returns_complete_validated_page() -> None:
    text = """<IfVersion repository="https://github.com/canton-network/splice" containsPullRequest={6123}>
New prose.
<Snippet source="https://github.com/canton-network/splice/pull/6123" path="file.yaml" language="yaml" />
<Else>
Existing prose.
<Snippet source="local://canton-network/splice/file.yaml" language="yaml" />
</Else>
</IfVersion>"""

    result = validate_authored_page(
        text, path=PATH, registry=REGISTRY, allow_local=True
    )

    assert result.diagnostics == ()
    assert len(result.conditions) == 1
    assert len(result.snippets) == 2


def test_returns_sorted_diagnostics_and_no_partial_page() -> None:
    text = """<Snippet source="unsupported" />
<IfVersion repository="not-a-url" containsPullRequest={0}>text</IfVersion>"""

    result = validate_authored_page(text, path=PATH, registry=REGISTRY)

    assert result.snippets == ()
    assert result.conditions == ()
    assert [diagnostic.span.start for diagnostic in result.diagnostics] == sorted(
        diagnostic.span.start for diagnostic in result.diagnostics
    )
    assert {diagnostic.code for diagnostic in result.diagnostics} >= {
        "SNIP008",
        "SNIP016",
        "SNIP021",
        "SNIP023",
    }
