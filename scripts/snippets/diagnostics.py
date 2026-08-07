from __future__ import annotations

from pathlib import Path

from .model import (
    Diagnostic,
    LocalSourcePolicyIssue,
    SnippetAttributeIssue,
    SnippetAttributeRule,
    SnippetSourceAttributeIssue,
    SnippetSourceAttributeRule,
    SnippetSourceSafetyIssue,
    SnippetSourceSafetyRule,
)

LOCAL_SOURCE_REMEDIATION = (
    "Run `npm run snippets:resolve-local -- --page <page.source.mdx>` before pushing."
)
SOURCE_ATTRIBUTE_CODES = {
    SnippetSourceAttributeRule.SOURCE_REQUIRED: "SNIP002",
    SnippetSourceAttributeRule.PATH_MUST_BE_QUOTED: "SNIP003",
    SnippetSourceAttributeRule.IMMUTABLE_PATH_FORBIDDEN: "SNIP004",
    SnippetSourceAttributeRule.PULL_REQUEST_PATH_REQUIRED: "SNIP005",
    SnippetSourceAttributeRule.LOCAL_PATH_FORBIDDEN: "SNIP006",
    SnippetSourceAttributeRule.UNSUPPORTED_SOURCE: "SNIP008",
}
SOURCE_SAFETY_CODES = {
    SnippetSourceSafetyRule.UNREGISTERED_REPOSITORY: "SNIP009",
    SnippetSourceSafetyRule.UNSAFE_PATH: "SNIP010",
}
SNIPPET_ATTRIBUTE_CODES = {
    SnippetAttributeRule.UNKNOWN_ATTRIBUTE: "SNIP015",
    SnippetAttributeRule.INVALID_LANGUAGE: "SNIP016",
    SnippetAttributeRule.INVALID_MARKERS: "SNIP017",
}


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


def snippet_source_attribute_diagnostics(
    path: Path, issues: tuple[SnippetSourceAttributeIssue, ...]
) -> tuple[Diagnostic, ...]:
    """Assign stable diagnostic codes to source/path attribute failures."""

    return tuple(
        Diagnostic(
            path=path,
            span=issue.span,
            code=SOURCE_ATTRIBUTE_CODES[issue.rule],
            message=issue.message,
        )
        for issue in issues
    )


def snippet_source_safety_diagnostics(
    path: Path, issues: tuple[SnippetSourceSafetyIssue, ...]
) -> tuple[Diagnostic, ...]:
    """Assign stable diagnostic codes to source-safety failures."""

    return tuple(
        Diagnostic(
            path=path,
            span=issue.span,
            code=SOURCE_SAFETY_CODES[issue.rule],
            message=issue.message,
        )
        for issue in issues
    )


def snippet_attribute_diagnostics(
    path: Path, issues: tuple[SnippetAttributeIssue, ...]
) -> tuple[Diagnostic, ...]:
    """Assign stable diagnostic codes to basic Snippet attribute failures."""

    return tuple(
        Diagnostic(
            path=path,
            span=issue.span,
            code=SNIPPET_ATTRIBUTE_CODES[issue.rule],
            message=issue.message,
        )
        for issue in issues
    )
