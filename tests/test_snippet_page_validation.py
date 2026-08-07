from __future__ import annotations

from pathlib import Path

from scripts.snippets.model import SnippetPageValidation
from scripts.snippets.page_validation import (
    validate_condition_page,
    validate_snippet_page,
)
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
COMMIT = "2c941ea9e834d7602d388f3271c0f864025ea756"


def validate(
    text: str, *, allow_local: bool = False
) -> SnippetPageValidation:
    conditions = validate_condition_page(text, path=PATH, registry=REGISTRY)
    return validate_snippet_page(
        text,
        path=PATH,
        registry=REGISTRY,
        conditions=conditions,
        allow_local=allow_local,
    )


def test_returns_validated_immutable_snippet() -> None:
    result = validate(
        f'<Snippet source="https://github.com/canton-network/splice/blob/{COMMIT}/file.yaml" '
        'language="yaml" />'
    )

    assert result.diagnostics == ()
    assert len(result.snippets) == 1
    assert result.snippets[0].condition is None


def test_returns_candidate_matching_condition() -> None:
    result = validate(
        """<IfVersion repository="https://github.com/canton-network/splice" containsPullRequest={6123}>
<Snippet source="https://github.com/canton-network/splice/pull/6123" path="file.yaml" language="yaml" />
</IfVersion>"""
    )

    assert result.diagnostics == ()
    assert result.snippets[0].condition is not None


def test_reports_candidate_identity_mismatch() -> None:
    result = validate(
        """<IfVersion repository="https://github.com/canton-network/splice" containsPullRequest={6123}>
<Snippet source="https://github.com/canton-network/splice/pull/6124" path="file.yaml" language="yaml" />
</IfVersion>"""
    )

    assert "SNIP028" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_reports_local_ref_remediation_unless_preview_enabled() -> None:
    text = (
        '<Snippet source="local://canton-network/splice/file.yaml" '
        'language="yaml" />'
    )

    committed = validate(text)
    preview = validate(text, allow_local=True)

    assert committed.diagnostics[0].code == "SNIP007"
    remediation = committed.diagnostics[0].remediation
    assert remediation is not None
    assert "snippets:resolve-local" in remediation
    assert preview.diagnostics == ()


def test_reports_snippet_syntax_error() -> None:
    result = validate('<Snippet source="one">')

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "SNIP014"
    ]
