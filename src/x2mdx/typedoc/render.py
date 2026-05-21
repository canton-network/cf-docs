"""Render TypeDoc reports into MDX pages."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from x2mdx.output import Page
from x2mdx.reference_pages import (
    DetailsHistoryChange,
    DetailsHistoryPage,
    DetailsHistoryVersionRow,
    ReferenceBadge,
    ReferenceCard,
    ReferenceMetaItem,
    ReferenceSection,
    render_details_history_page,
)
from x2mdx.templating import markdown_page


def escape_md_cell(text: str) -> str:
    return text.replace("|", r"\|").replace("\n", "<br/>")


def render_change_summary(change_details: list[dict[str, object]]) -> str:
    parts: list[str] = []
    for entry in change_details:
        version = str(entry["version"])
        changes = entry["changes"] if isinstance(entry.get("changes"), list) else []
        rendered_changes = "; ".join(str(change) for change in changes) if changes else "details updated"
        parts.append(f"`{version}`: {rendered_changes}")
    return "<br/>".join(parts) if parts else "-"


def render_summary_cell(text: str) -> str:
    summary = text.strip()
    return escape_md_cell(summary) if summary else "-"


def version_change_summary_rows(exports: list[dict[str, object]], versions: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for version in versions:
        added = sum(1 for export in exports if export["introduced_in"] == version)
        changed = sum(
            1
            for export in exports
            if any(str(entry["version"]) == version for entry in export["change_details"])
        )
        removed = sum(1 for export in exports if export["removed_in"] == version)
        rows.append(
            [
                f"`{version}`",
                f"`{added}`" if added else "-",
                f"`{changed}`" if changed else "-",
                f"`{removed}`" if removed else "-",
            ]
        )
    return rows


def version_rows(exports: list[dict[str, object]], versions: list[str]) -> list[DetailsHistoryVersionRow]:
    rows: list[DetailsHistoryVersionRow] = []
    for version in versions:
        added = sum(1 for export in exports if export["introduced_in"] == version)
        changed = sum(
            1
            for export in exports
            if any(str(entry["version"]) == version for entry in export["change_details"])
        )
        removed = sum(1 for export in exports if export["removed_in"] == version)
        deprecated = sum(
            1
            for export in exports
            if export["lifecycle_label"] == "Deprecated" and export["introduced_in"] == version
        )
        replaced = sum(1 for export in exports if export["replaces"] and export["introduced_in"] == version)
        rows.append(
            DetailsHistoryVersionRow(
                version=version,
                added=str(added),
                changed=str(changed),
                removed=str(removed),
                deprecated=str(deprecated or "-"),
                replaced=str(replaced or "-"),
            )
        )
    return rows


def build_details_history_page(
    report,
    *,
    output_path: str,
    page_title: str,
    page_description: str,
    reference_href: str,
) -> Page:
    exports_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for export in report.exports:
        exports_by_group[str(export["group"])].append(export)

    inventory_sections: list[ReferenceSection] = []
    for group_title in report.export_groups:
        exports = exports_by_group.get(group_title)
        if not exports:
            continue
        inventory_sections.append(
            ReferenceSection(
                heading=group_title,
                cards=[
                    ReferenceCard(
                        title=str(export["name"]),
                        href=f"{reference_href}#{export['anchor']}",
                        summary=str(export["summary"] or "-"),
                        badges=[
                            ReferenceBadge(f"Since {export['introduced_in']}", tone="added"),
                            *(
                                [ReferenceBadge(str(export["lifecycle_label"]), tone="deprecated" if export["lifecycle_label"] == "Deprecated" else "neutral")]
                                if export["lifecycle_label"]
                                else []
                            ),
                            *(
                                [ReferenceBadge(f"Changed {export['change_details'][-1]['version']}", tone="changed")]
                                if export["change_details"]
                                else []
                            ),
                            *(
                                [ReferenceBadge(f"Removed {export['removed_in']}", tone="removed")]
                                if export["removed_in"]
                                else []
                            ),
                        ],
                        meta_items=[
                            ReferenceMetaItem("Kind", str(export["kind_label"])),
                            ReferenceMetaItem("Introduced", str(export["introduced_in"])),
                            ReferenceMetaItem("Removed", str(export["removed_in"] or "-")),
                        ],
                    )
                    for export in exports
                ],
            )
        )

    changes: list[DetailsHistoryChange] = []
    for export in report.exports:
        href = f"{reference_href}#{export['anchor']}"
        if export["introduced_in"] != report.versions[0]:
            changes.append(
                DetailsHistoryChange(
                    version=str(export["introduced_in"]),
                    title=f"Added {export['name']}",
                    details=str(export["kind_label"]),
                    tone="added",
                    href=href,
                )
            )
        for entry in export["change_details"]:
            changes.append(
                DetailsHistoryChange(
                    version=str(entry["version"]),
                    title=f"Changed {export['name']}",
                    details="; ".join(str(change) for change in entry["changes"]),
                    tone="changed",
                    href=href,
                )
            )
        if export["removed_in"]:
            changes.append(
                DetailsHistoryChange(
                    version=str(export["removed_in"]),
                    title=f"Removed {export['name']}",
                    details=str(export["kind_label"]),
                    tone="removed",
                    href=href,
                )
            )

    page = DetailsHistoryPage(
        path=output_path,
        title=f"{page_title} details and history",
        description=page_description,
        eyebrow="Details and history",
        summary="Generated-source metadata, version coverage, export inventory, and per-version changes for this source stream.",
        badges=[ReferenceBadge("TypeDoc", tone="protocol"), ReferenceBadge(report.publish_version, tone="neutral")],
        meta_items=[
            ReferenceMetaItem("Source stream", report.package_name),
            ReferenceMetaItem("Publish version", report.publish_version),
            ReferenceMetaItem("Versions compared", ", ".join(report.versions)),
        ],
        source_items=[
            ReferenceMetaItem("Input family", report.source_name),
            ReferenceMetaItem("Version filter", report.version_filter),
            ReferenceMetaItem("Package", report.package_name),
        ],
        source_cards=[
            ReferenceCard(
                title="Generated reference page",
                summary="The TypeScript reference page is generated from the publish-version TypeDoc JSON, with history calculated across selected snapshots.",
                meta_items=[ReferenceMetaItem("Exports", str(len(report.exports)))],
            )
        ],
        version_rows=version_rows(report.exports, report.versions),
        inventory_sections=inventory_sections,
        changes=sorted(changes, key=lambda change: (report.versions.index(change.version) if change.version in report.versions else 999, change.title)),
        limitations=[
            "Change detection is structural and compares selected TypeDoc JSON inputs; it does not infer behavioral compatibility.",
            "Lifecycle labels and replacement links are included only when parsed from supported TypeDoc metadata.",
        ],
    )
    return render_details_history_page(page)


def _type_parameter_rows(items: list[dict[str, Any]]) -> list[list[str]]:
    return [
        [
            f"`{escape_md_cell(item['name'])}`",
            f"`{escape_md_cell(item['constraint'])}`" if item["constraint"] else "-",
            f"`{escape_md_cell(item['default'])}`" if item["default"] else "-",
            escape_md_cell(item["description"]) if item["description"] else "-",
        ]
        for item in items
    ]


def _signature_docs(signature_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "declaration": str(signature["declaration"]),
            "summary": signature["summary"],
            "type_parameter_rows": _type_parameter_rows(signature["type_parameters"]),
            "parameter_rows": [
                [
                    f"`{escape_md_cell(item['name'])}`",
                    f"`{escape_md_cell(item['type'])}`",
                    item["required"],
                    escape_md_cell(item["description"]) if item["description"] else "-",
                ]
                for item in signature["parameters"]
            ],
            "returns": str(signature["returns"]),
        }
        for signature in signature_docs
    ]


def _export_context(export: dict[str, Any]) -> dict[str, Any]:
    lifecycle_bits = [
        f"Kind: `{export['kind_label']}`",
        f"Introduced: `{export['introduced_in']}`",
    ]
    if export["lifecycle_label"]:
        lifecycle_bits.append(f"Lifecycle: `{export['lifecycle_label']}`")
    if export["replaces"]:
        lifecycle_bits.append(f"Replaces: `{export['replaces']}`")
    if export["deprecated_text"]:
        lifecycle_bits.append(f"Deprecated: {export['deprecated_text']}")
    if export["change_details"]:
        lifecycle_bits.append("Changed in: " + ", ".join(f"`{entry['version']}`" for entry in export["change_details"]))
    if export["removed_in"]:
        lifecycle_bits.append(f"Removed in: `{export['removed_in']}`")
        lifecycle_bits.append("Shown for historical reference.")
    if export["source_location"]:
        lifecycle_bits.append(f"Source: `{export['source_location']}`")

    return {
        "anchor": str(export["anchor"]),
        "name": str(export["name"]),
        "lifecycle_bits": lifecycle_bits,
        "change_rows": [
            [
                f"`{escape_md_cell(str(entry['version']))}`",
                escape_md_cell("; ".join(str(change) for change in entry["changes"])),
            ]
            for entry in export["change_details"]
        ],
        "signature": export["signature"],
        "summary": export["summary"],
        "type_parameter_rows": _type_parameter_rows(export["type_parameters"]),
        "signature_docs": _signature_docs(export["signature_docs"]),
        "member_rows": [
            [
                f"`{escape_md_cell(item['name'])}`",
                f"`{escape_md_cell(item['type'])}`",
                escape_md_cell(item["summary"]) if item["summary"] else "-",
            ]
            for item in export["members"]
        ],
    }


def build_page(
    report,
    *,
    output_path: str,
    page_title: str,
    page_description: str,
) -> Page:
    exports_by_group: dict[str, list[dict[str, object]]] = defaultdict(list)
    for export in report.exports:
        exports_by_group[export["group"]].append(export)

    grouped_exports = []
    for group_title in report.export_groups:
        exports = exports_by_group.get(group_title)
        if exports:
            grouped_exports.append({"title": group_title, "exports": [_export_context(export) for export in exports]})

    return markdown_page(
        path=output_path,
        title=page_title,
        description=page_description,
        template_name="typedoc/page.md.j2",
        report=report,
        toc_rows=[
            [
                f"[`{escape_md_cell(export['name'])}`](#{export['anchor']})",
                escape_md_cell(export["kind_label"]),
                render_summary_cell(str(export["summary"])),
                f"`{export['introduced_in']}`",
                escape_md_cell(render_change_summary(export["change_details"])),
                f"`{export['lifecycle_label']}`" if export["lifecycle_label"] == "Deprecated" else "-",
                f"`{export['removed_in']}`" if export["removed_in"] else "-",
            ]
            for export in report.exports
        ],
        version_change_summary_rows=version_change_summary_rows(report.exports, report.versions),
        grouped_exports=grouped_exports,
    )
