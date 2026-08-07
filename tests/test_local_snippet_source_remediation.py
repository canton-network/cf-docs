from __future__ import annotations

from pathlib import Path

from scripts.snippets.diagnostics import local_source_policy_diagnostic
from scripts.snippets.model import LocalSourcePolicyIssue, Span


def test_reports_resolve_local_command_at_source_location() -> None:
    diagnostic = local_source_policy_diagnostic(
        Path("docs-main/validator.source.mdx"),
        LocalSourcePolicyIssue(
            span=Span(start=20, end=30, line=7, column=3),
            message=(
                "Local snippet references are preview-only and cannot be committed"
            ),
        ),
    )

    assert diagnostic.code == "SNIP007"
    assert diagnostic.span.line == 7
    assert diagnostic.span.column == 3
    assert diagnostic.remediation == (
        "Run `npm run snippets:resolve-local -- --page <page.source.mdx>` "
        "before pushing."
    )
