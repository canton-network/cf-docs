from __future__ import annotations

from pathlib import Path

from scripts.snippets.model import Diagnostic, Span


def test_formats_page_line_column_code_and_message() -> None:
    diagnostic = Diagnostic(
        path=Path("docs-main/validator.source.mdx"),
        span=Span(start=20, end=30, line=7, column=3),
        code="SNIP008",
        message="Unsupported snippet source",
    )

    assert diagnostic.format() == (
        "docs-main/validator.source.mdx:7:3: "
        "SNIP008: Unsupported snippet source"
    )


def test_appends_remediation_on_indented_line() -> None:
    diagnostic = Diagnostic(
        path=Path("docs-main/validator.source.mdx"),
        span=Span(start=20, end=30, line=7, column=3),
        code="SNIP007",
        message="Local snippet references are preview-only",
        remediation="Resolve the local reference before pushing.",
    )

    assert diagnostic.format().endswith(
        "\n  remediation: Resolve the local reference before pushing."
    )
