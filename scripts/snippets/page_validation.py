from __future__ import annotations

from pathlib import Path

from .diagnostics import (
    directive_syntax_diagnostic,
    if_version_attribute_diagnostics,
    if_version_structure_diagnostics,
)
from .model import ConditionPageValidation, IfVersionTag
from .registry import RepositoryRegistry
from .syntax import DirectiveSyntaxError, parse_if_version_tags
from .validation import (
    validate_if_version_attributes,
    validate_if_version_structure,
)


def validate_condition_page(
    text: str, *, path: Path, registry: RepositoryRegistry
) -> ConditionPageValidation:
    """Parse and validate conditional declarations without inspecting snippets."""

    try:
        tags = parse_if_version_tags(text)
    except DirectiveSyntaxError as error:
        return ConditionPageValidation(
            tags=(),
            conditions=(),
            diagnostics=(directive_syntax_diagnostic(path, error),),
        )

    diagnostics = list(
        if_version_structure_diagnostics(
            path, validate_if_version_structure(text, tags)
        )
    )
    conditions = []
    for tag in tags:
        if not isinstance(tag, IfVersionTag) or tag.closing:
            continue
        result = validate_if_version_attributes(tag, registry)
        diagnostics.extend(if_version_attribute_diagnostics(path, result.issues))
        if result.condition is not None:
            conditions.append(result.condition)
    return ConditionPageValidation(
        tags=tags,
        conditions=tuple(conditions),
        diagnostics=tuple(diagnostics),
    )
