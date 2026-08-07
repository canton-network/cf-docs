from __future__ import annotations

from pathlib import Path

from .model import Diagnostic, LocalSourcePolicyIssue

LOCAL_SOURCE_REMEDIATION = (
    "Run `npm run snippets:resolve-local -- --page <page.source.mdx>` before pushing."
)


def local_source_policy_diagnostic(
    path: Path, issue: LocalSourcePolicyIssue
) -> Diagnostic:
    """Add committed-page remediation to a local-ref policy failure."""

    return Diagnostic(
        path=path,
        span=issue.span,
        code="SNIP007",
        message=issue.message,
        remediation=LOCAL_SOURCE_REMEDIATION,
    )
