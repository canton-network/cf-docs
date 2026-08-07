from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from .model import (
    ConditionStructureIssue,
    ConditionStructureRule,
    ElseTag,
    IfVersionAttributeIssue,
    IfVersionAttributeRule,
    IfVersionAttributeValidation,
    IfVersionCondition,
    IfVersionTag,
    ImmutableSourceReference,
    LocalSourcePolicyIssue,
    LocalSourceReference,
    PullRequestSnippetSource,
    SnippetSourceSafetyIssue,
    SnippetSourceSafetyRule,
    SnippetTag,
    Span,
)
from .references import parse_github_repository_url
from .registry import RepositoryRegistry

SAFE_LANGUAGE_RE = re.compile(r"[A-Za-z0-9_+.-]+")
IF_VERSION_ATTRIBUTES = {"repository", "containsPullRequest"}
SNIPPET_ATTRIBUTES = {
    "source",
    "path",
    "startAfter",
    "endBefore",
    "lines",
    "normalize",
    "trim",
    "stripTrailingWhitespace",
    "replaceFrom",
    "replaceWith",
    "language",
}


def is_safe_source_path(value: str) -> bool:
    """Return whether a repository-relative path cannot escape its source."""

    path = PurePosixPath(value)
    return (
        bool(path.parts)
        and not value.startswith(("/", "\\"))
        and "\\" not in value
        and ".." not in path.parts
    )


def is_registered_repository(
    repository: str, registry: RepositoryRegistry
) -> bool:
    """Return whether a source repository appears in the explicit allowlist."""

    return registry.get(repository) is not None


def is_safe_language(value: str | int | None) -> bool:
    """Return whether a language is a non-empty safe fence identifier."""

    return isinstance(value, str) and SAFE_LANGUAGE_RE.fullmatch(value) is not None


def has_valid_marker_pair(
    start_after: str | int | None, end_before: str | int | None
) -> bool:
    """Return whether marker extraction is absent or a valid complete pair."""

    if start_after is None and end_before is None:
        return True
    return (
        isinstance(start_after, str)
        and isinstance(end_before, str)
        and bool(start_after)
        and bool(end_before)
        and start_after != end_before
    )


@dataclass
class _IfFrame:
    opening: IfVersionTag
    else_count: int = 0
    else_end: int | None = None


def validate_if_version_structure(
    text: str, tags: tuple[IfVersionTag | ElseTag, ...]
) -> tuple[ConditionStructureIssue, ...]:
    """Validate conditional tag nesting without interpreting attributes."""

    issues: list[ConditionStructureIssue] = []
    stack: list[IfVersionTag | ElseTag] = []
    frames: dict[int, _IfFrame] = {}

    for tag in tags:
        if isinstance(tag, IfVersionTag) and not tag.closing:
            stack.append(tag)
            frames[tag.span.start] = _IfFrame(opening=tag)
            continue
        if isinstance(tag, ElseTag) and not tag.closing:
            if not stack or not isinstance(stack[-1], IfVersionTag):
                issues.append(
                    ConditionStructureIssue(
                        rule=ConditionStructureRule.ELSE_NOT_DIRECT_CHILD,
                        span=tag.span,
                        message="Else must be a direct child of IfVersion",
                    )
                )
            else:
                frame = frames[stack[-1].span.start]
                frame.else_count += 1
                if frame.else_count > 1:
                    issues.append(
                        ConditionStructureIssue(
                            rule=ConditionStructureRule.MULTIPLE_ELSE,
                            span=tag.span,
                            message="IfVersion can contain at most one Else branch",
                        )
                    )
            stack.append(tag)
            continue

        expected_type = ElseTag if isinstance(tag, ElseTag) else IfVersionTag
        if not stack or not isinstance(stack[-1], expected_type):
            expected = type(stack[-1]).__name__ if stack else "nothing"
            name = "Else" if isinstance(tag, ElseTag) else "IfVersion"
            issues.append(
                ConditionStructureIssue(
                    rule=ConditionStructureRule.UNEXPECTED_CLOSE,
                    span=tag.span,
                    message=f"Unexpected </{name}>; expected {expected}",
                )
            )
            continue

        opening = stack.pop()
        if isinstance(tag, ElseTag):
            if stack and isinstance(stack[-1], IfVersionTag):
                frames[stack[-1].span.start].else_end = tag.span.end
            continue

        if not isinstance(opening, IfVersionTag):
            continue
        frame = frames.pop(opening.span.start)
        if (
            frame.else_end is not None
            and text[frame.else_end : tag.span.start].strip()
        ):
            issues.append(
                ConditionStructureIssue(
                    rule=ConditionStructureRule.ELSE_NOT_FINAL,
                    span=tag.span,
                    message="Else must be the final content in IfVersion",
                )
            )

    for opening in reversed(stack):
        name = "Else" if isinstance(opening, ElseTag) else "IfVersion"
        issues.append(
            ConditionStructureIssue(
                rule=ConditionStructureRule.UNCLOSED_TAG,
                span=opening.span,
                message=f"Unclosed <{name}> tag",
            )
        )
    return tuple(issues)


def validate_if_version_attributes(
    tag: IfVersionTag, registry: RepositoryRegistry
) -> IfVersionAttributeValidation:
    """Validate one opening IfVersion tag without applying nesting rules."""

    if tag.closing:
        raise ValueError("Cannot validate attributes on a closing IfVersion tag")

    issues: list[IfVersionAttributeIssue] = []
    unknown = sorted(
        attribute.name
        for attribute in tag.attributes
        if attribute.name not in IF_VERSION_ATTRIBUTES
    )
    if unknown:
        issues.append(
            IfVersionAttributeIssue(
                rule=IfVersionAttributeRule.UNKNOWN_ATTRIBUTE,
                span=tag.span,
                message=f"Unknown IfVersion attribute(s): {', '.join(unknown)}",
            )
        )

    repository_value = tag.attribute("repository")
    repository = (
        parse_github_repository_url(repository_value)
        if isinstance(repository_value, str)
        else None
    )
    if repository is None:
        issues.append(
            IfVersionAttributeIssue(
                rule=IfVersionAttributeRule.INVALID_REPOSITORY,
                span=tag.span,
                message=(
                    "IfVersion repository must be a complete GitHub repository URL"
                ),
            )
        )
    elif not is_registered_repository(repository, registry):
        issues.append(
            IfVersionAttributeIssue(
                rule=IfVersionAttributeRule.UNREGISTERED_REPOSITORY,
                span=tag.span,
                message=f"Repository {repository!r} is not allowlisted",
            )
        )

    candidate = tag.attribute("containsPullRequest")
    if not isinstance(candidate, int) or candidate < 1:
        issues.append(
            IfVersionAttributeIssue(
                rule=IfVersionAttributeRule.INVALID_PULL_REQUEST,
                span=tag.span,
                message=(
                    "IfVersion containsPullRequest must be a positive integer "
                    "expression"
                ),
            )
        )

    condition = None
    if (
        repository is not None
        and is_registered_repository(repository, registry)
        and isinstance(candidate, int)
        and candidate > 0
    ):
        condition = IfVersionCondition(
            repository=repository,
            contains_pull_request=candidate,
            span=tag.span,
        )
    return IfVersionAttributeValidation(
        condition=condition, issues=tuple(issues)
    )


def unknown_snippet_attributes(tag: SnippetTag) -> tuple[str, ...]:
    """Return unsupported Snippet attribute names in deterministic order."""

    return tuple(
        sorted(
            attribute.name
            for attribute in tag.attributes
            if attribute.name not in SNIPPET_ATTRIBUTES
        )
    )


def validate_snippet_source_safety(
    source: (
        ImmutableSourceReference | PullRequestSnippetSource | LocalSourceReference
    ),
    *,
    span: Span,
    registry: RepositoryRegistry,
) -> tuple[SnippetSourceSafetyIssue, ...]:
    """Apply repository allowlist and path-safety policy to a resolved source."""

    issues: list[SnippetSourceSafetyIssue] = []
    if not is_registered_repository(source.repository, registry):
        issues.append(
            SnippetSourceSafetyIssue(
                rule=SnippetSourceSafetyRule.UNREGISTERED_REPOSITORY,
                span=span,
                message=f"Repository {source.repository!r} is not allowlisted",
            )
        )
    if not is_safe_source_path(source.path):
        issues.append(
            SnippetSourceSafetyIssue(
                rule=SnippetSourceSafetyRule.UNSAFE_PATH,
                span=span,
                message=f"Unsafe source path {source.path!r}",
            )
        )
    return tuple(issues)


def validate_local_source_policy(
    source: (
        ImmutableSourceReference | PullRequestSnippetSource | LocalSourceReference
    ),
    *,
    span: Span,
    allow_local: bool,
) -> tuple[LocalSourcePolicyIssue, ...]:
    """Reject preview-only local refs unless the caller opts into preview mode."""

    if isinstance(source, LocalSourceReference) and not allow_local:
        return (
            LocalSourcePolicyIssue(
                span=span,
                message=(
                    "Local snippet references are preview-only and cannot be committed"
                ),
            ),
        )
    return ()
