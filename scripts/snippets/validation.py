from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from .model import (
    ConditionStructureIssue,
    ConditionStructureRule,
    ElseTag,
    IfVersionTag,
)
from .registry import RepositoryRegistry

SAFE_LANGUAGE_RE = re.compile(r"[A-Za-z0-9_+.-]+")


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
