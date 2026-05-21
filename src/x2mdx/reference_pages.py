"""Shared Mintlify-like reference page structures and rendering helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from x2mdx.output import Page, RawMarkdown
from x2mdx.templating import render_template


@dataclass(frozen=True)
class ReferenceBadge:
    label: str
    tone: str = "neutral"


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

    @property
    def status_label(self) -> str:
        primary = self.status_primary_badge
        if primary is None:
            return "Current"
        return primary.label

    @property
    def status_tone(self) -> str:
        primary = self.status_primary_badge
        if primary is None:
            return "neutral"
        if primary.label.lower().startswith("deprecated"):
            return "deprecated"
        return primary.tone

    @property
    def status_chips(self) -> list[ReferenceBadge]:
        primary = self.status_primary_badge
        ignored = {"protocol", "neutral"}
        chips: list[ReferenceBadge] = []
        for badge in self.badges:
            if badge == primary or badge.tone in ignored:
                continue
            chips.append(badge)
        return chips

    @property
    def status_primary_badge(self) -> ReferenceBadge | None:
        priority = [
            lambda badge: badge.label.lower().startswith("removed"),
            lambda badge: badge.label.lower().startswith("since"),
            lambda badge: badge.label.lower().startswith("changed"),
            lambda badge: badge.label.lower().startswith("deprecated"),
        ]
        for predicate in priority:
            match = next((badge for badge in self.badges if predicate(badge)), None)
            if match is not None:
                return match
        return next((badge for badge in self.badges if badge.tone not in {"protocol", "neutral"}), None)


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
class DetailsHistoryVersionRow:
    version: str
    added: str = "-"
    changed: str = "-"
    removed: str = "-"
    deprecated: str = "-"
    replaced: str = "-"

    @property
    def status_items(self) -> list["DetailsHistoryStatusItem"]:
        entries = [
            ("added", self.added, "added"),
            ("changed", self.changed, "changed"),
            ("removed", self.removed, "removed"),
            ("deprecated", self.deprecated, "deprecated"),
            ("replaced", self.replaced, "replaced"),
        ]
        items = [
            DetailsHistoryStatusItem(label=label, value=value, tone=tone)
            for label, value, tone in entries
            if has_meaningful_count(value)
        ]
        if items:
            return items
        return [DetailsHistoryStatusItem(label="surface changes", value="0", tone="neutral")]

    @property
    def summary(self) -> str:
        items = self.status_items
        if len(items) == 1 and items[0].tone == "neutral":
            return "No surface changes detected in the selected inputs."
        return ", ".join(f"{item.value} {item.label}" for item in items) + "."


@dataclass(frozen=True)
class DetailsHistoryStatusItem:
    label: str
    value: str
    tone: str = "neutral"


@dataclass(frozen=True)
class DetailsHistoryChange:
    version: str
    title: str
    details: str = ""
    tone: str = "changed"
    href: str | None = None


@dataclass(frozen=True)
class DetailsHistoryPage:
    path: str
    title: str
    description: str | None = None
    eyebrow: str | None = None
    summary: str | None = None
    back_link: str | None = None
    back_label: str | None = None
    badges: list[ReferenceBadge] = field(default_factory=list)
    meta_items: list[ReferenceMetaItem] = field(default_factory=list)
    source_items: list[ReferenceMetaItem] = field(default_factory=list)
    source_cards: list[ReferenceCard] = field(default_factory=list)
    version_rows: list[DetailsHistoryVersionRow] = field(default_factory=list)
    inventory_sections: list[ReferenceSection] = field(default_factory=list)
    changes: list[DetailsHistoryChange] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


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


def markdown_page_from_template(
    *,
    path: str,
    title: str,
    description: str | None,
    template_name: str,
    **context: Any,
) -> Page:
    return Page(
        path=path,
        title=title,
        description=safe_markdown_text(description) if description is not None else None,
        blocks=[RawMarkdown(render_template(template_name, collapse_blank_lines=False, **context))],
    )


def render_collection_page(page: ReferenceCollectionPage) -> Page:
    return markdown_page_from_template(
        path=page.path,
        title=page.title,
        description=page.description,
        template_name="reference/collection.md.j2",
        page=page,
    )


def render_details_history_page(page: DetailsHistoryPage) -> Page:
    body = render_template("reference/details_history.md.j2", collapse_blank_lines=False, page=page)
    body = "\n".join(line.rstrip() for line in body.splitlines())
    return Page(
        path=page.path,
        title=page.title,
        description=page.description,
        blocks=[RawMarkdown(body)],
    )


def render_operation_page(page: ReferenceOperationPage) -> Page:
    return markdown_page_from_template(
        path=page.path,
        title=page.title,
        description=None,
        template_name="reference/operation.md.j2",
        page=page,
    )


def compact_text(text: str, *, limit: int = 160) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return ""
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def has_meaningful_count(value: str) -> bool:
    normalized = str(value or "").strip()
    return bool(normalized and normalized not in {"-", "0"})


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

    example = ReferenceExample(title=name, body=json_body(sample)) if sample is not None else None
    return ReferenceSchema(
        name=name,
        summary=summary or infer_type_label(sample),
        description=description,
        anchor=anchor,
        fields=fields,
        example=example,
    )
