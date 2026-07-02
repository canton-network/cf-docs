"""Render TypeDoc reports into MDX pages."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from x2mdx.output import Page
from x2mdx.templating import markdown_page


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


def _export_context(export: dict[str, Any]) -> dict[str, Any]:
    lifecycle_bits = [
        f"Kind: `{export['kind_label']}`",
        f"Introduced: `{export['introduced_in']}`",
    ]
    if export["lifecycle_label"]:
        lifecycle_bits.append(f"Lifecycle: `{export['lifecycle_label']}`")
    if export["replaces"]:
        lifecycle_bits.append(f"Replaces: `{escape_mdx_text(export['replaces'])}`")
    if export["deprecated_text"]:
        lifecycle_bits.append(f"Deprecated: {escape_mdx_text(export['deprecated_text'])}")
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
                f"[{code_span(export['name'])}](#{export['anchor']})",
                escape_md_cell(export["kind_label"]),
                render_summary_cell(str(export["summary"])),
                code_span(export["introduced_in"]),
                escape_md_cell(render_change_summary(export["change_details"])),
                code_span(export["lifecycle_label"]) if export["lifecycle_label"] == "Deprecated" else "-",
                code_span(export["removed_in"]) if export["removed_in"] else "-",
            ]
            for export in report.exports
        ],
        version_change_summary_rows=version_change_summary_rows(report.exports, report.versions),
        grouped_exports=grouped_exports,
    )
