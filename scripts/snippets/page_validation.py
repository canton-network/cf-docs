from __future__ import annotations

from pathlib import Path

from .diagnostics import (
    candidate_condition_diagnostics,
    directive_syntax_diagnostic,
    if_version_attribute_diagnostics,
    if_version_structure_diagnostics,
    local_source_policy_diagnostic,
    snippet_attribute_diagnostics,
    snippet_source_attribute_diagnostics,
    snippet_source_safety_diagnostics,
)
from .model import (
    ConditionPageValidation,
    IfVersionTag,
    SnippetPageValidation,
    ValidatedSnippet,
)
from .registry import RepositoryRegistry
from .semantics import (
    map_snippet_condition_contexts,
    resolve_snippet_source_attributes,
    validate_candidate_condition,
    validate_snippet_basic_attributes,
)
from .syntax import (
    DirectiveSyntaxError,
    parse_if_version_tags,
    parse_snippet_tags,
)
from .validation import (
    validate_if_version_attributes,
    validate_if_version_structure,
    validate_local_source_policy,
    validate_snippet_source_safety,
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


def validate_snippet_page(
    text: str,
    *,
    path: Path,
    registry: RepositoryRegistry,
    conditions: ConditionPageValidation,
    allow_local: bool = False,
) -> SnippetPageValidation:
    """Parse and validate snippets against prevalidated condition context."""

    try:
        tags = parse_snippet_tags(text)
    except DirectiveSyntaxError as error:
        return SnippetPageValidation(
            snippets=(),
            diagnostics=(directive_syntax_diagnostic(path, error),),
        )

    diagnostics = []
    snippets = []
    contexts = map_snippet_condition_contexts(
        tags, conditions.tags, conditions.conditions
    )
    for context in contexts:
        tag = context.snippet
        tag_diagnostics = list(
            snippet_attribute_diagnostics(
                path, validate_snippet_basic_attributes(tag)
            )
        )
        source_result = resolve_snippet_source_attributes(tag)
        tag_diagnostics.extend(
            snippet_source_attribute_diagnostics(path, source_result.issues)
        )
        source = source_result.source
        if source is not None:
            tag_diagnostics.extend(
                snippet_source_safety_diagnostics(
                    path,
                    validate_snippet_source_safety(
                        source, span=tag.span, registry=registry
                    ),
                )
            )
            local_issues = validate_local_source_policy(
                source, span=tag.span, allow_local=allow_local
            )
            tag_diagnostics.extend(
                local_source_policy_diagnostic(path, issue)
                for issue in local_issues
            )
            tag_diagnostics.extend(
                candidate_condition_diagnostics(
                    path, validate_candidate_condition(source, context)
                )
            )
        diagnostics.extend(tag_diagnostics)
        if source is not None and not tag_diagnostics:
            snippets.append(
                ValidatedSnippet(
                    tag=tag,
                    source=source,
                    condition=context.condition,
                )
            )
    return SnippetPageValidation(
        snippets=tuple(snippets), diagnostics=tuple(diagnostics)
    )
