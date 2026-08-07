from __future__ import annotations

from .model import (
    ImmutableSourceReference,
    LocalSourceReference,
    PullRequestSnippetSource,
    PullRequestSourceReference,
    SnippetSourceAttributeIssue,
    SnippetSourceAttributeRule,
    SnippetSourceAttributeValidation,
    SnippetTag,
)
from .references import parse_source_reference


def resolve_snippet_source_attributes(
    tag: SnippetTag,
) -> SnippetSourceAttributeValidation:
    """Resolve source/path attributes without applying repository policy."""

    issues: list[SnippetSourceAttributeIssue] = []
    source_value = tag.attribute("source")
    path_value = tag.attribute("path")
    if not isinstance(source_value, str):
        issues.append(
            SnippetSourceAttributeIssue(
                rule=SnippetSourceAttributeRule.SOURCE_REQUIRED,
                span=tag.span,
                message="Snippet requires a quoted source attribute",
            )
        )
        return SnippetSourceAttributeValidation(None, tuple(issues))
    if path_value is not None and not isinstance(path_value, str):
        issues.append(
            SnippetSourceAttributeIssue(
                rule=SnippetSourceAttributeRule.PATH_MUST_BE_QUOTED,
                span=tag.span,
                message="Snippet path must be quoted",
            )
        )
        return SnippetSourceAttributeValidation(None, tuple(issues))

    reference = parse_source_reference(source_value)
    if reference is None:
        issues.append(
            SnippetSourceAttributeIssue(
                rule=SnippetSourceAttributeRule.UNSUPPORTED_SOURCE,
                span=tag.span,
                message="Unsupported snippet source",
            )
        )
        return SnippetSourceAttributeValidation(None, tuple(issues))

    source: (
        ImmutableSourceReference | PullRequestSnippetSource | LocalSourceReference
    )
    if isinstance(reference, ImmutableSourceReference):
        source = reference
        if path_value is not None:
            issues.append(
                SnippetSourceAttributeIssue(
                    rule=SnippetSourceAttributeRule.IMMUTABLE_PATH_FORBIDDEN,
                    span=tag.span,
                    message="Immutable blob source already contains its path",
                )
            )
    elif isinstance(reference, PullRequestSourceReference):
        if not path_value:
            issues.append(
                SnippetSourceAttributeIssue(
                    rule=SnippetSourceAttributeRule.PULL_REQUEST_PATH_REQUIRED,
                    span=tag.span,
                    message="Pull-request source requires a quoted path attribute",
                )
            )
            return SnippetSourceAttributeValidation(None, tuple(issues))
        source = PullRequestSnippetSource(
            repository=reference.repository,
            pull_request=reference.pull_request,
            path=path_value,
        )
    else:
        source = reference
        if path_value is not None:
            issues.append(
                SnippetSourceAttributeIssue(
                    rule=SnippetSourceAttributeRule.LOCAL_PATH_FORBIDDEN,
                    span=tag.span,
                    message="Local source already contains its path",
                )
            )
    return SnippetSourceAttributeValidation(source, tuple(issues))
