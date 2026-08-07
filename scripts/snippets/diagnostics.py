from __future__ import annotations

from pathlib import Path

from .model import (
    CandidateConditionIssue,
    CandidateConditionRule,
    ConditionStructureIssue,
    ConditionStructureRule,
    Diagnostic,
    DirectiveSyntaxRule,
    IfVersionAttributeIssue,
    IfVersionAttributeRule,
    LocalSourcePolicyIssue,
    SnippetAttributeIssue,
    SnippetAttributeRule,
    SnippetSourceAttributeIssue,
    SnippetSourceAttributeRule,
    SnippetSourceSafetyIssue,
    SnippetSourceSafetyRule,
)
from .syntax import DirectiveSyntaxError

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
IF_VERSION_ATTRIBUTE_CODES = {
    IfVersionAttributeRule.UNKNOWN_ATTRIBUTE: "SNIP020",
    IfVersionAttributeRule.INVALID_REPOSITORY: "SNIP021",
    IfVersionAttributeRule.UNREGISTERED_REPOSITORY: "SNIP022",
    IfVersionAttributeRule.INVALID_PULL_REQUEST: "SNIP023",
}
IF_VERSION_STRUCTURE_CODES = {
    ConditionStructureRule.UNEXPECTED_CLOSE: "SNIP012",
    ConditionStructureRule.ELSE_NOT_DIRECT_CHILD: "SNIP025",
    ConditionStructureRule.UNCLOSED_TAG: "SNIP026",
    ConditionStructureRule.MULTIPLE_ELSE: "SNIP029",
    ConditionStructureRule.ELSE_NOT_FINAL: "SNIP030",
}
CANDIDATE_CONDITION_CODES = {
    CandidateConditionRule.CONDITION_REQUIRED: "SNIP027",
    CandidateConditionRule.IDENTITY_MISMATCH: "SNIP028",
}
DIRECTIVE_SYNTAX_CODES = {
    DirectiveSyntaxRule.CLOSING_ATTRIBUTES: "SNIP011",
    DirectiveSyntaxRule.MALFORMED_ATTRIBUTES: "SNIP013",
    DirectiveSyntaxRule.DUPLICATE_ATTRIBUTE: "SNIP013",
    DirectiveSyntaxRule.SNIPPET_NOT_SELF_CLOSING: "SNIP014",
    DirectiveSyntaxRule.IF_VERSION_SELF_CLOSING: "SNIP019",
    DirectiveSyntaxRule.ELSE_SELF_CLOSING: "SNIP024",
    DirectiveSyntaxRule.ELSE_ATTRIBUTES: "SNIP024",
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


def if_version_attribute_diagnostics(
    path: Path, issues: tuple[IfVersionAttributeIssue, ...]
) -> tuple[Diagnostic, ...]:
    """Assign stable diagnostic codes to IfVersion attribute failures."""

    return tuple(
        Diagnostic(
            path=path,
            span=issue.span,
            code=IF_VERSION_ATTRIBUTE_CODES[issue.rule],
            message=issue.message,
        )
        for issue in issues
    )


def if_version_structure_diagnostics(
    path: Path, issues: tuple[ConditionStructureIssue, ...]
) -> tuple[Diagnostic, ...]:
    """Assign stable diagnostic codes to conditional structure failures."""

    return tuple(
        Diagnostic(
            path=path,
            span=issue.span,
            code=IF_VERSION_STRUCTURE_CODES[issue.rule],
            message=issue.message,
        )
        for issue in issues
    )


def candidate_condition_diagnostics(
    path: Path, issues: tuple[CandidateConditionIssue, ...]
) -> tuple[Diagnostic, ...]:
    """Assign stable diagnostic codes to candidate-condition failures."""

    return tuple(
        Diagnostic(
            path=path,
            span=issue.span,
            code=CANDIDATE_CONDITION_CODES[issue.rule],
            message=issue.message,
        )
        for issue in issues
    )


def directive_syntax_diagnostic(
    path: Path, error: DirectiveSyntaxError
) -> Diagnostic:
    """Assign a stable diagnostic code to one directive parser failure."""

    return Diagnostic(
        path=path,
        span=error.span,
        code=DIRECTIVE_SYNTAX_CODES[error.rule],
        message=str(error),
    )
