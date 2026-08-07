from __future__ import annotations

from .model import (
    CandidateConditionIssue,
    CandidateConditionRule,
    ElseTag,
    IfVersionCondition,
    IfVersionTag,
    ImmutableSourceReference,
    LocalSourceReference,
    PullRequestSnippetSource,
    PullRequestSourceReference,
    SnippetAttributeIssue,
    SnippetAttributeRule,
    SnippetConditionContext,
    SnippetSourceAttributeIssue,
    SnippetSourceAttributeRule,
    SnippetSourceAttributeValidation,
    SnippetTag,
)
from .references import parse_source_reference
from .validation import (
    has_valid_marker_pair,
    is_safe_language,
    unknown_snippet_attributes,
)


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


def validate_snippet_basic_attributes(
    tag: SnippetTag,
) -> tuple[SnippetAttributeIssue, ...]:
    """Validate names, language, and marker pairing without resolving source."""

    issues: list[SnippetAttributeIssue] = []
    unknown = unknown_snippet_attributes(tag)
    if unknown:
        issues.append(
            SnippetAttributeIssue(
                rule=SnippetAttributeRule.UNKNOWN_ATTRIBUTE,
                span=tag.span,
                message=f"Unknown Snippet attribute(s): {', '.join(unknown)}",
            )
        )
    if not is_safe_language(tag.attribute("language")):
        issues.append(
            SnippetAttributeIssue(
                rule=SnippetAttributeRule.INVALID_LANGUAGE,
                span=tag.span,
                message="Snippet requires a safe quoted language attribute",
            )
        )
    if not has_valid_marker_pair(
        tag.attribute("startAfter"), tag.attribute("endBefore")
    ):
        issues.append(
            SnippetAttributeIssue(
                rule=SnippetAttributeRule.INVALID_MARKERS,
                span=tag.span,
                message=(
                    "Snippet markers must be distinct, non-empty quoted strings, "
                    "and marker extraction requires both startAfter and endBefore"
                ),
            )
        )
    return tuple(issues)


def map_snippet_condition_contexts(
    snippets: tuple[SnippetTag, ...],
    conditional_tags: tuple[IfVersionTag | ElseTag, ...],
    conditions: tuple[IfVersionCondition, ...],
) -> tuple[SnippetConditionContext, ...]:
    """Associate snippets with their innermost enclosing IfVersion condition."""

    conditions_by_start = {
        condition.span.start: condition for condition in conditions
    }
    events = sorted(
        (*snippets, *conditional_tags), key=lambda event: event.span.start
    )
    stack: list[IfVersionCondition | None] = []
    contexts: list[SnippetConditionContext] = []
    for event in events:
        if isinstance(event, IfVersionTag):
            if event.closing:
                if stack:
                    stack.pop()
            else:
                stack.append(conditions_by_start.get(event.span.start))
        elif isinstance(event, SnippetTag):
            contexts.append(
                SnippetConditionContext(
                    snippet=event,
                    condition=stack[-1] if stack else None,
                )
            )
    return tuple(contexts)


def validate_candidate_condition(
    source: (
        ImmutableSourceReference | PullRequestSnippetSource | LocalSourceReference
    ),
    context: SnippetConditionContext,
) -> tuple[CandidateConditionIssue, ...]:
    """Require candidate source identity to match its enclosing condition."""

    if not isinstance(source, PullRequestSnippetSource):
        return ()
    condition = context.condition
    if condition is None:
        return (
            CandidateConditionIssue(
                rule=CandidateConditionRule.CONDITION_REQUIRED,
                span=context.snippet.span,
                message="Candidate pull-request snippet must be inside IfVersion",
            ),
        )
    if (
        source.repository != condition.repository
        or source.pull_request != condition.contains_pull_request
    ):
        return (
            CandidateConditionIssue(
                rule=CandidateConditionRule.IDENTITY_MISMATCH,
                span=context.snippet.span,
                message=(
                    "Candidate snippet does not match its enclosing IfVersion "
                    f"({condition.repository}#{condition.contains_pull_request})"
                ),
            ),
        )
    return ()
