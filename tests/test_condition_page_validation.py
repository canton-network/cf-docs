from __future__ import annotations

from pathlib import Path

from scripts.snippets.model import ConditionPageValidation
from scripts.snippets.page_validation import validate_condition_page
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


def validate(text: str) -> ConditionPageValidation:
    return validate_condition_page(text, path=PATH, registry=REGISTRY)


def test_returns_validated_condition() -> None:
    result = validate(
        """<IfVersion repository="https://github.com/canton-network/splice" containsPullRequest={6123}>
new
</IfVersion>"""
    )

    assert result.diagnostics == ()
    assert len(result.conditions) == 1
    assert result.conditions[0].repository == "canton-network/splice"


def test_reports_conditional_syntax_error() -> None:
    result = validate(
        '<IfVersion repository="https://github.com/canton-network/splice" />'
    )

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "SNIP019"
    ]


def test_reports_conditional_structure_error() -> None:
    result = validate("<Else>orphan</Else>")

    assert "SNIP025" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_reports_condition_attribute_error() -> None:
    result = validate(
        '<IfVersion repository="not-a-url" containsPullRequest={6123}>'
        "new</IfVersion>"
    )

    assert "SNIP021" in {
        diagnostic.code for diagnostic in result.diagnostics
    }
