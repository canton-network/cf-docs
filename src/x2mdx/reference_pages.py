"""Shared Mintlify-like reference page structures and rendering helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from x2mdx.history.events import history_event_anchor
from x2mdx.history.models import (
    HistoryEvent,
    HistoryEventKind,
    HistoryItem,
    LifecycleState,
)
from x2mdx.output import FrontmatterValue, Page, RawMarkdown
from x2mdx.templating import render_template


@dataclass(frozen=True)
class ReferenceBadge:
    label: str
    tone: str = "neutral"
    href: str | None = None


@dataclass(frozen=True)
class ReferenceMetaItem:
    label: str
    value: str
    href: str | None = None


@dataclass(frozen=True)
class ReferenceBreadcrumb:
    label: str
    href: str | None = None


@dataclass(frozen=True)
class ReferenceField:
    name: str
    type_label: str
    required: bool = False
    description: str = ""
    location: str | None = None
    default: str | None = None
    api_type_label: str | None = None


@dataclass(frozen=True)
class ReferenceExample:
    title: str
    body: str
    language: str = "json"
    kind: str = "request"
    media_type: str | None = None


@dataclass(frozen=True)
class ReferenceSchema:
    name: str
    summary: str = ""
    description: str = ""
    anchor: str | None = None
    fields: list[ReferenceField] = field(default_factory=list)
    variants: list["ReferenceSchema"] = field(default_factory=list)
    enum_values: list[str] = field(default_factory=list)
    example: ReferenceExample | None = None


@dataclass(frozen=True)
class ReferencePanel:
    title: str
    summary: str = ""
    description: str = ""
    badges: list[ReferenceBadge] = field(default_factory=list)
    meta_items: list[ReferenceMetaItem] = field(default_factory=list)
    schema: ReferenceSchema | None = None
    example: ReferenceExample | None = None


@dataclass(frozen=True)
class ReferenceCard:
    title: str
    href: str | None = None
    summary: str = ""
    badges: list[ReferenceBadge] = field(default_factory=list)
    meta_items: list[ReferenceMetaItem] = field(default_factory=list)


@dataclass(frozen=True)
class ReferenceSection:
    heading: str
    body_markdown: str | None = None
    cards: list[ReferenceCard] = field(default_factory=list)
    meta_items: list[ReferenceMetaItem] = field(default_factory=list)
    schemas: list[ReferenceSchema] = field(default_factory=list)
    examples: list[ReferenceExample] = field(default_factory=list)


@dataclass(frozen=True)
class ReferenceCollectionPage:
    path: str
    title: str
    description: str | None = None
    eyebrow: str | None = None
    summary: str | None = None
    back_link: str | None = None
    back_label: str | None = None
    badges: list[ReferenceBadge] = field(default_factory=list)
    meta_items: list[ReferenceMetaItem] = field(default_factory=list)
    sections: list[ReferenceSection] = field(default_factory=list)


@dataclass(frozen=True)
class ReferenceChange:
    version: str
    details: str


@dataclass(frozen=True)
class ReferenceOperationPage:
    path: str
    title: str
    anchor: str | None = None
    description: str | None = None
    eyebrow: str | None = None
    summary: str | None = None
    back_link: str | None = None
    back_label: str | None = None
    breadcrumbs: list[ReferenceBreadcrumb] = field(default_factory=list)
    badges: list[ReferenceBadge] = field(default_factory=list)
    meta_items: list[ReferenceMetaItem] = field(default_factory=list)
    operation_method: str | None = None
    operation_target: str | None = None
    overview_markdown: str | None = None
    protocol_items: list[ReferenceMetaItem] = field(default_factory=list)
    inputs: list[ReferencePanel] = field(default_factory=list)
    outputs: list[ReferencePanel] = field(default_factory=list)
    examples: list[ReferenceExample] = field(default_factory=list)
    lifecycle_changes: list[ReferenceChange] = field(default_factory=list)
    related_schemas: list[ReferenceSchema] = field(default_factory=list)
    history_events: list[HistoryEvent] = field(default_factory=list)
    api_frontmatter: str | None = None
    auth_method: str | None = None
    playground: str | None = None


def markdown_page_from_template(
    *,
    path: str,
    title: str,
    description: str | None,
    template_name: str,
    frontmatter: dict[str, FrontmatterValue] | None = None,
    **context: Any,
) -> Page:
    return Page(
        path=path,
        title=title,
        description=safe_markdown_text(description)
        if description is not None
        else None,
        frontmatter=frontmatter or {},
        blocks=[
            RawMarkdown(
                render_template(template_name, collapse_blank_lines=False, **context)
            )
        ],
    )


def render_collection_page(page: ReferenceCollectionPage) -> Page:
    return markdown_page_from_template(
        path=page.path,
        title=page.title,
        description=page.description,
        template_name="reference/collection.md.j2",
        page=page,
    )


def render_operation_page(page: ReferenceOperationPage) -> Page:
    frontmatter: dict[str, FrontmatterValue] = {}
    if page.api_frontmatter is not None:
        frontmatter["api"] = page.api_frontmatter
    if page.auth_method is not None:
        frontmatter["authMethod"] = page.auth_method
    if page.playground is not None:
        frontmatter["playground"] = page.playground
    return markdown_page_from_template(
        path=page.path,
        title=page.title,
        description=None,
        template_name="reference/operation.md.j2",
        frontmatter=frontmatter,
        page=page,
    )


def reference_badges_for_history_item(
    item: HistoryItem,
    *,
    kind_label: str,
) -> list[ReferenceBadge]:
    badges = [ReferenceBadge(kind_label, "protocol")]
    badges.append(
        ReferenceBadge(
            f"Added {item.first_seen}",
            "added",
            f"#{history_event_anchor(HistoryEventKind.INTRODUCED, item.first_seen)}",
        )
    )
    if item.last_changed is not None:
        badges.append(
            ReferenceBadge(
                f"Updated {item.last_changed}",
                "changed",
                f"#{history_event_anchor(HistoryEventKind.CHANGED, item.last_changed)}",
            )
        )
    deprecated_transition = next(
        (
            transition
            for transition in reversed(item.lifecycle_transitions)
            if transition.state == LifecycleState.DEPRECATED
        ),
        None,
    )
    if deprecated_transition is not None:
        badges.append(
            ReferenceBadge(
                f"Deprecated {deprecated_transition.version}",
                "removed",
                f"#{history_event_anchor(HistoryEventKind.DEPRECATED, deprecated_transition.version)}",
            )
        )
    if item.remove_as_of is not None:
        badges.append(
            ReferenceBadge(
                f"Removal scheduled {item.remove_as_of}",
                "removed",
                f"#{history_event_anchor(HistoryEventKind.REMOVE_AS_OF, item.remove_as_of)}",
            )
        )
    return badges


def reference_badges_for_history_events(
    events: list[HistoryEvent],
    *,
    kind_label: str,
) -> list[ReferenceBadge]:
    """Build reader-facing lifecycle badges from newest-first history events."""
    badges = [ReferenceBadge(kind_label, "protocol")]
    definitions = (
        (HistoryEventKind.INTRODUCED, "Added", "added"),
        (HistoryEventKind.CHANGED, "Updated", "changed"),
        (HistoryEventKind.DEPRECATED, "Deprecated", "removed"),
        (HistoryEventKind.REMOVE_AS_OF, "Removal scheduled", "removed"),
    )
    for kind, label, tone in definitions:
        event = next((candidate for candidate in events if candidate.kind == kind), None)
        if event is None:
            continue
        badges.append(
            ReferenceBadge(
                f"{label} {event.version}",
                tone,
                f"#{history_event_anchor(event.kind, event.version)}",
            )
        )
    return badges


def compact_text(text: str, *, limit: int = 160) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return ""
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def safe_markdown_text(text: str) -> str:
    return str(text or "").replace("<", "&lt;")


def relative_page_ref(from_path: Path, to_path: Path) -> str:
    relative = os.path.relpath(to_path.with_suffix(""), start=from_path.parent)
    link = Path(relative).as_posix()
    if not link.startswith("."):
        return f"./{link}"
    return link


def rooted_page_ref(root_prefix: str, target_path: Path, output_dir: Path) -> str:
    relative = target_path.relative_to(output_dir).with_suffix("").as_posix()
    trimmed = root_prefix.strip()
    if not trimmed or trimmed == "/":
        return f"/{relative}"
    return f"/{trimmed.strip('/')}/{relative}"


def code_literal(value: str) -> str:
    escaped = str(value).replace("`", r"\`")
    return f"`{escaped}`"


def json_body(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def infer_type_label(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        if not value:
            return "array"
        return f"array[{infer_type_label(value[0])}]"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return "string"


def schema_from_sample(
    *,
    name: str,
    sample: Any,
    required_fields: list[str] | None = None,
    description: str = "",
    summary: str = "",
    anchor: str | None = None,
    variants: list[ReferenceSchema] | None = None,
) -> ReferenceSchema:
    required = set(required_fields or [])
    fields: list[ReferenceField] = []
    if isinstance(sample, dict):
        for key, value in sample.items():
            fields.append(
                ReferenceField(
                    name=str(key),
                    type_label=infer_type_label(value),
                    required=key in required,
                )
            )
    elif isinstance(sample, list):
        fields.append(
            ReferenceField(
                name="items",
                type_label=infer_type_label(sample[0]) if sample else "unknown",
                required=True,
            )
        )

    example = (
        ReferenceExample(title=name, body=json_body(sample))
        if sample is not None
        else None
    )
    return ReferenceSchema(
        name=name,
        summary=summary or infer_type_label(sample),
        description=description,
        anchor=anchor,
        fields=fields,
        variants=variants or [],
        example=example,
    )
