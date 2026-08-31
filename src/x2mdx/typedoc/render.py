"""Render TypeDoc reports into MDX pages."""

from __future__ import annotations

from collections import defaultdict
from functools import cmp_to_key
from typing import Any

from x2mdx.history.events import history_events_for_item
from x2mdx.history.models import HistoryEvent, HistoryEventKind, SurfaceHistoryReport
from x2mdx.history.versioning import compare_versions
from x2mdx.output import Page
from x2mdx.reference_pages import (
    ReferenceBadge,
    ReferenceMetaItem,
    reference_badges_for_history_events,
)
from x2mdx.templating import markdown_page
from x2mdx.typedoc.history import typedoc_item_id


def escape_md_cell(text: str) -> str:
    return "<br/>".join(escape_mdx_text(line).replace("|", r"\|") for line in text.splitlines())


def escape_md_code(text: str) -> str:
    return str(text).replace("`", r"\`").replace("|", r"\|").replace("\n", " ").strip()


def code_span(text: str) -> str:
    return f"`{escape_md_code(text)}`"


def escape_mdx_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_change_summary(change_details: list[dict[str, object]]) -> str:
    parts: list[str] = []
    for entry in change_details:
        version = str(entry["version"])
        raw_changes = entry.get("changes")
        changes: list[object] = raw_changes if isinstance(raw_changes, list) else []
        rendered_changes = "; ".join(str(change) for change in changes) if changes else "details updated"
        parts.append(f"`{version}`: {rendered_changes}")
    return "<br/>".join(parts) if parts else "-"


def render_summary_cell(text: str) -> str:
    summary = text.strip()
    return escape_md_cell(summary) if summary else "-"


def _type_parameter_rows(items: list[dict[str, Any]]) -> list[list[str]]:
    return [
        [
            code_span(item["name"]),
            code_span(item["constraint"]) if item["constraint"] else "-",
            code_span(item["default"]) if item["default"] else "-",
            escape_md_cell(item["description"]) if item["description"] else "-",
        ]
        for item in items
    ]


def _signature_docs(signature_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "declaration": str(signature["declaration"]),
            "summary": escape_mdx_text(signature["summary"]),
            "type_parameter_rows": _type_parameter_rows(signature["type_parameters"]),
            "parameter_rows": [
                [
                    code_span(item["name"]),
                    code_span(item["type"]),
                    item["required"],
                    escape_md_cell(item["description"]) if item["description"] else "-",
                ]
                for item in signature["parameters"]
            ],
            "returns": escape_md_code(str(signature["returns"])),
        }
        for signature in signature_docs
    ]


def _export_context(
    export: dict[str, Any],
    *,
    package_name: str,
    history_report: SurfaceHistoryReport | None,
) -> dict[str, Any]:
    lifecycle_bits = [
        f"Kind: `{export['kind_label']}`",
    ]
    if export["lifecycle_label"]:
        lifecycle_bits.append(f"Lifecycle: `{export['lifecycle_label']}`")
    if export["replaces"]:
        lifecycle_bits.append(f"Replaces: `{escape_mdx_text(export['replaces'])}`")
    if export["deprecated_text"]:
        lifecycle_bits.append(f"Deprecated: {escape_mdx_text(export['deprecated_text'])}")
    if export["source_location"]:
        lifecycle_bits.append(f"Source: `{export['source_location']}`")

    if history_report is not None:
        item = history_report.items_by_id()[
            typedoc_item_id(package_name, str(export["key"]))
        ]
        badges = reference_badges_for_history_events(
            list(
                history_events_for_item(
                    item,
                    comparison_versions=history_report.comparison_versions,
                )
            ),
            kind_label=str(export["kind_label"]),
        )
    else:
        badges = [
            ReferenceBadge(str(export["kind_label"]), "protocol"),
            ReferenceBadge(f"Added {export['introduced_in']}", "added"),
        ]

    return {
        "anchor": str(export["anchor"]),
        "name": str(export["name"]),
        "badges": badges,
        "lifecycle_bits": lifecycle_bits,
        "change_rows": [
            [
                code_span(str(entry["version"])),
                escape_md_cell("; ".join(str(change) for change in entry["changes"])),
            ]
            for entry in export["change_details"]
        ],
        "signature": export["signature"],
        "summary": escape_mdx_text(export["summary"]),
        "type_parameter_rows": _type_parameter_rows(export["type_parameters"]),
        "signature_docs": _signature_docs(export["signature_docs"]),
        "member_rows": [
            [
                code_span(item["name"]),
                code_span(item["type"]),
                escape_md_cell(item["summary"]) if item["summary"] else "-",
            ]
            for item in export["members"]
        ],
    }


def package_history_events(history_report: SurfaceHistoryReport) -> list[HistoryEvent]:
    grouped: dict[tuple[HistoryEventKind, str], list[tuple[str, HistoryEvent]]] = defaultdict(list)
    for item in history_report.current_items():
        symbol_name = item.id.rsplit("::", 1)[-1]
        for event in history_events_for_item(
            item,
            comparison_versions=history_report.comparison_versions,
        ):
            grouped[(event.kind, event.version)].append((symbol_name, event))

    events: list[HistoryEvent] = []
    for (kind, version), entries in grouped.items():
        details: tuple[str, ...]
        if kind == HistoryEventKind.INTRODUCED:
            noun = f"exported symbol{'s' if len(entries) != 1 else ''}"
            verb = "present." if entries[0][1].label == "Present since at least" else "added."
            details = (f"{len(entries)} {noun} {verb}",)
        elif kind in {HistoryEventKind.DEPRECATED, HistoryEventKind.REMOVE_AS_OF}:
            details = tuple(sorted({name for name, _ in entries}, key=str.casefold))
        else:
            details = tuple(
                f"{name}: {detail.replace('`', '')}"
                for name, event in entries
                for detail in (event.details or (event.label,))
            )
        events.append(
            HistoryEvent(
                kind=kind,
                version=version,
                label=entries[0][1].label,
                details=details,
                evidence=tuple(
                    dict.fromkeys(
                        evidence
                        for _, event in entries
                        for evidence in event.evidence
                    )
                ),
            )
        )

    priority = {
        HistoryEventKind.REMOVE_AS_OF: 0,
        HistoryEventKind.DEPRECATED: 1,
        HistoryEventKind.CHANGED: 2,
        HistoryEventKind.INTRODUCED: 3,
        HistoryEventKind.REPLACEMENT: 4,
    }

    def compare(left: HistoryEvent, right: HistoryEvent) -> int:
        version_comparison = compare_versions(
            left.version,
            right.version,
            known_order=history_report.comparison_versions,
        )
        if version_comparison:
            return -version_comparison
        return priority[left.kind] - priority[right.kind]

    return sorted(events, key=cmp_to_key(compare))


def build_page(
    report,
    *,
    output_path: str,
    page_title: str,
    page_description: str,
    history_report: SurfaceHistoryReport | None = None,
) -> Page:
    current_exports = [export for export in report.exports if export["status"] == "active"]
    exports_by_group: dict[str, list[dict[str, object]]] = defaultdict(list)
    for export in current_exports:
        exports_by_group[export["group"]].append(export)

    grouped_exports = []
    for group_title in report.export_groups:
        exports = exports_by_group.get(group_title)
        if exports:
            grouped_exports.append(
                {
                    "title": group_title,
                    "exports": [
                        _export_context(
                            export,
                            package_name=report.package_name,
                            history_report=history_report,
                        )
                        for export in exports
                    ],
                }
            )

    history_events = package_history_events(history_report) if history_report else []
    page_badges = (
        reference_badges_for_history_events(
            history_events,
            kind_label="TypeScript",
        )
        if history_report
        else [ReferenceBadge("TypeScript", "protocol")]
    )

    return markdown_page(
        path=output_path,
        title=page_title,
        description=page_description,
        template_name="typedoc/page.md.j2",
        report=report,
        page_title=page_title,
        page_summary=page_description,
        page_badges=page_badges,
        page_meta_items=[
            ReferenceMetaItem("Package", report.package_name),
            ReferenceMetaItem("Current release", report.publish_version),
            ReferenceMetaItem("Compared releases", str(len(report.versions))),
        ],
        toc_rows=[
            [
                f"[{code_span(export['name'])}](#{export['anchor']})",
                escape_md_cell(export["kind_label"]),
                render_summary_cell(str(export["summary"])),
                code_span(export["introduced_in"]),
                escape_md_cell(render_change_summary(export["change_details"])),
                code_span(export["lifecycle_label"]) if export["lifecycle_label"] == "Deprecated" else "-",
                "-",
            ]
            for export in current_exports
        ],
        grouped_exports=grouped_exports,
        history_events=history_events,
    )
