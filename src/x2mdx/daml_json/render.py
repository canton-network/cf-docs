"""Render Daml docs JSON reports into MDX pages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from x2mdx.daml_json.models import DamlDocsReport
from x2mdx.output import Page, RawMarkdown
from x2mdx.reference_pages import (
    ReferenceBadge,
    ReferenceCard,
    ReferenceCollectionPage,
    ReferenceMetaItem,
    ReferenceSection,
    render_collection_page,
    safe_markdown_text,
)
from x2mdx.templating import markdown_page, render_template

EXCLUDED_MODULE_NAMES = frozenset(
    {
        "GHC.Show.Text",
        "GHC.Tuple.Check",
        "Ghc.Show.Text",
        "Ghc.Tuple.Check",
    }
)
ACRONYM_PARTS = {
    "da": "DA",
    "ghc": "GHC",
    "lf": "LF",
}
REPLACED_BY_RE = re.compile(r"^Replaced by: (?P<target>[A-Za-z][A-Za-z0-9_.]*[A-Za-z0-9])\.$")
MARKDOWN_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def escape_md_cell(text: str) -> str:
    return text.replace("|", r"\|").replace("\n", "<br/>")


def normalize_markdown_autolinks(text: str) -> str:
    return MARKDOWN_AUTOLINK_RE.sub(lambda match: f"[{match.group(1)}]({match.group(1)})", text)


def render_doc_blocks(descr: Any) -> str:
    if not descr:
        return ""
    if isinstance(descr, str):
        return normalize_markdown_autolinks(descr.strip())

    paragraphs = descr if isinstance(descr, list) else [descr]
    blocks: list[str] = []
    for paragraph in paragraphs:
        if isinstance(paragraph, list):
            lines: list[str] = []
            for line in paragraph:
                if isinstance(line, list):
                    lines.extend(str(item) for item in line)
                else:
                    lines.append(str(line))
            raw = "\n".join(lines).strip()
            has_doctest = any(line.lstrip().startswith(">>>") for line in lines)
            has_fence = any(line.strip().startswith("```") for line in lines)
            if has_doctest and not has_fence:
                raw = f"```text\n{raw}\n```"
        else:
            raw = str(paragraph).strip()
        if raw:
            blocks.append(normalize_markdown_autolinks(raw))
    return "\n\n".join(blocks)


def extract_tagged_warning_messages(warns: Any, tag: str) -> list[str]:
    values: list[Any]
    if warns is None:
        values = []
    elif isinstance(warns, list):
        values = warns
    else:
        values = [warns]

    out: list[str] = []

    def append_texts(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                append_texts(item)
            return
        if node is None:
            return
        text = str(node).strip()
        if text:
            out.append(text)

    for entry in values:
        if not isinstance(entry, dict):
            continue
        if tag in entry:
            append_texts(entry[tag])

    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def module_display_name(module_name: str) -> str:
    parts = [part for part in module_name.split(".") if part]
    if not parts:
        return module_name
    normalized: list[str] = []
    for part in parts:
        mapped = ACRONYM_PARTS.get(part.lower())
        if mapped:
            normalized.append(mapped)
        elif part.isupper():
            normalized.append(part)
        elif part.islower():
            normalized.append(part.capitalize())
        else:
            normalized.append(part)
    return ".".join(normalized)


def compact_text(text: str, *, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return "-"
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def strip_markdown_summary(text: str) -> str:
    summary = text.strip()
    if not summary:
        return ""
    summary = summary.replace("`", "")
    summary = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", summary)
    summary = re.sub(r"\*\*([^*]+)\*\*", r"\1", summary)
    summary = re.sub(r"_([^_]+)_", r"\1", summary)
    summary = re.sub(r"<[^>]+>", "", summary)
    return summary


def module_summary_preview(module_doc: dict[str, Any]) -> str:
    rendered = render_doc_blocks(module_doc.get("md_descr"))
    if not rendered:
        return "-"
    for chunk in rendered.split("\n\n"):
        stripped = strip_markdown_summary(chunk)
        normalized = compact_text(stripped)
        if normalized != "-":
            return normalized
    return "-"


def normalize_type_lit(value: Any) -> str:
    text = str(value)
    match = re.fullmatch(r'(["\'])([A-Za-z_][A-Za-z0-9_]*)\1', text)
    if match:
        return match.group(2)
    return text


def as_union(node: dict[str, Any]) -> tuple[str, Any]:
    if len(node) != 1:
        raise ValueError(f"Expected tagged union object, got keys={list(node.keys())}")
    [(tag, payload)] = node.items()
    return tag, payload


def render_type(ty: Any, prec: int = 0) -> str:
    if not isinstance(ty, dict):
        return str(ty)
    tag, payload = as_union(ty)
    if tag == "TypeApp":
        _ref, name, args = payload
        rendered_args = [render_type(arg, 2) for arg in args]
        text = " ".join([str(name), *rendered_args]).strip()
        return f"({text})" if prec >= 2 and args else text
    if tag == "TypeFun":
        parts = [render_type(part, 1) for part in payload]
        text = " -> ".join(parts)
        return f"({text})" if prec >= 1 else text
    if tag == "TypeList":
        return f"[{render_type(payload, 0)}]"
    if tag == "TypeTuple":
        items = [render_type(part, 0) for part in payload]
        return items[0] if len(items) == 1 else f"({', '.join(items)})"
    if tag == "TypeLit":
        return normalize_type_lit(payload)
    return str(ty)


def render_context(ctx: list[Any]) -> str:
    if not ctx:
        return ""
    items = [render_type(item, 0) for item in ctx]
    return f"{items[0]} => " if len(items) == 1 else f"({', '.join(items)}) => "


def render_fields_table(fields: list[dict[str, Any]]) -> str:
    if not fields:
        return "(no fields)"
    rows = [
        "| Field | Type | Description |",
        "| :---- | :--- | :---------- |",
    ]
    for field in fields:
        rows.append(
            f"| {escape_md_cell(str(field['fd_name']))} | "
            f"{escape_md_cell(render_type(field['fd_type']))} | "
            f"{escape_md_cell(render_doc_blocks(field.get('fd_descr')))} |"
        )
    return "\n".join(rows)


def render_instance(inst: dict[str, Any]) -> str:
    return f"instance {render_context(inst.get('id_context', []))}{render_type(inst['id_type'])}"


def render_warn_blocks(warns: Any) -> list[str]:
    warning_messages = extract_tagged_warning_messages(warns, "WarnData")
    deprecation_messages = extract_tagged_warning_messages(warns, "DeprecatedData")
    blocks: list[str] = []
    for message in warning_messages:
        blocks.append("\n".join(["<Warning>", message, "</Warning>"]))
    for message in deprecation_messages:
        blocks.append("\n".join(["<Warning>", f"Deprecated: {message}", "</Warning>"]))
    return blocks


def extract_exact_replacement_target(messages: list[str]) -> str | None:
    for message in messages:
        match = REPLACED_BY_RE.fullmatch(message.strip())
        if match:
            return match.group("target")
    return None


def render_function(fn: dict[str, Any]) -> str:
    name = str(fn["fct_name"])
    anchor = fn.get("fct_anchor")
    signature = f"{name} : {render_context(fn.get('fct_context', []))}{render_type(fn['fct_type'])}"
    parts: list[str] = []
    if anchor:
        parts.append(f'<span id="{anchor}"></span>')
    parts.append(f"### `{name}`")
    parts.append(f"```daml\n{signature}\n```")
    descr = render_doc_blocks(fn.get("fct_descr"))
    if descr:
        parts.append(descr)
    return "\n\n".join(parts)


def render_choice(choice: dict[str, Any]) -> str:
    name = str(choice.get("cd_name", ""))
    anchor = choice.get("cd_anchor")
    parts: list[str] = []
    if anchor:
        parts.append(f'<span id="{anchor}"></span>')
    parts.append(f"#### Choice `{name}`")
    desc = render_doc_blocks(choice.get("cd_descr"))
    if desc:
        parts.append(desc)
    parts.extend(render_warn_blocks(choice.get("cd_warns")))
    controllers = choice.get("cd_controller") or []
    if controllers:
        parts.append("Controllers: " + ", ".join(f"`{item}`" for item in controllers))
    choice_type = choice.get("cd_type")
    if choice_type:
        parts.append(f"Returns: `{render_type(choice_type)}`")
    fields = choice.get("cd_fields") or []
    if fields:
        parts.append("Arguments:")
        parts.append(render_fields_table(fields))
    return "\n\n".join(parts)


def render_template_doc(template: dict[str, Any]) -> str:
    name = str(template.get("td_name", ""))
    anchor = template.get("td_anchor")
    parts: list[str] = []
    if anchor:
        parts.append(f'<span id="{anchor}"></span>')
    parts.append(f"### Template `{name}`")
    desc = render_doc_blocks(template.get("td_descr"))
    if desc:
        parts.append(desc)
    parts.extend(render_warn_blocks(template.get("td_warns")))
    signatory = template.get("td_signatory") or []
    if signatory:
        parts.append("Signatories: " + ", ".join(f"`{item}`" for item in signatory))
    payload = template.get("td_payload") or []
    if payload:
        parts.append("Payload:")
        parts.append(render_fields_table(payload))
    interface_instances = template.get("td_interfaceInstances") or []
    if interface_instances:
        lines = ["Interface Instances:"]
        lines.extend(
            f"- `{render_type(item.get('ii_interface'))}` for `{render_type(item.get('ii_template'))}`"
            for item in interface_instances
        )
        parts.append("\n".join(lines))
    choices = template.get("td_choices") or []
    if choices:
        parts.append("Choices:")
        parts.append("\n\n".join(render_choice(choice) for choice in choices))
    return "\n\n".join(parts)


def render_interface_method(method: dict[str, Any]) -> str:
    name = str(method.get("mtd_name", ""))
    anchor = method.get("mtd_anchor")
    parts: list[str] = []
    if anchor:
        parts.append(f'<span id="{anchor}"></span>')
    parts.append(f"#### Method `{name}`")
    desc = render_doc_blocks(method.get("mtd_descr"))
    if desc:
        parts.append(desc)
    parts.extend(render_warn_blocks(method.get("mtd_warns")))
    method_type = method.get("mtd_type")
    if method_type:
        parts.append(f"Type: `{render_type(method_type)}`")
    return "\n\n".join(parts)


def render_interface(interface: dict[str, Any]) -> str:
    name = str(interface.get("if_name", ""))
    anchor = interface.get("if_anchor")
    parts: list[str] = []
    if anchor:
        parts.append(f'<span id="{anchor}"></span>')
    parts.append(f"### Interface `{name}`")
    desc = render_doc_blocks(interface.get("if_descr"))
    if desc:
        parts.append(desc)
    parts.extend(render_warn_blocks(interface.get("if_warns")))
    viewtype = interface.get("if_viewtype")
    if isinstance(viewtype, dict):
        raw_view = viewtype.get("unInterfaceViewtypeDoc", viewtype)
        parts.append(f"View Type: `{render_type(raw_view)}`")
    choices = interface.get("if_choices") or []
    if choices:
        parts.append("Choices:")
        parts.append("\n\n".join(render_choice(choice) for choice in choices))
    methods = interface.get("if_methods") or []
    if methods:
        parts.append("Methods:")
        parts.append("\n\n".join(render_interface_method(method) for method in methods))
    interface_instances = interface.get("if_interfaceInstances") or []
    if interface_instances:
        lines = ["Interface Instances:"]
        lines.extend(
            f"- `{render_type(item.get('ii_interface'))}` for `{render_type(item.get('ii_template'))}`"
            for item in interface_instances
        )
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def render_class_method(method: dict[str, Any]) -> str:
    name = str(method["cm_name"])
    signature = f"{name} : {render_context(method.get('cm_localContext', []))}{render_type(method['cm_type'])}"
    desc = render_doc_blocks(method.get("cm_descr"))
    out = [f"- `{signature}`"]
    if desc:
        out.append(f"  {desc.replace(chr(10), chr(10) + '  ')}")
    return "\n".join(out)


def render_class(cls: dict[str, Any]) -> str:
    name = str(cls["cl_name"])
    anchor = cls.get("cl_anchor")
    args = " ".join(cls.get("cl_args", []))
    header = f"class {render_context(cls.get('cl_super', []))}{name}"
    if args:
        header = f"{header} {args}"
    parts: list[str] = []
    if anchor:
        parts.append(f'<span id="{anchor}"></span>')
    parts.append(f"### `{header}`")
    desc = render_doc_blocks(cls.get("cl_descr"))
    if desc:
        parts.append(desc)
    methods = cls.get("cl_methods", [])
    if methods:
        parts.append("Methods:")
        parts.append("\n".join(render_class_method(method) for method in methods))
    instances = cls.get("cl_instances", [])
    if instances:
        parts.append("Instances:")
        parts.append("\n".join(f"- `{render_instance(instance)}`" for instance in instances))
    return "\n\n".join(parts)


def render_constructor(constructor: dict[str, Any]) -> str:
    tag, payload = as_union(constructor)
    name = str(payload["ac_name"])
    anchor = payload.get("ac_anchor")
    parts: list[str] = []
    if anchor:
        parts.append(f'<span id="{anchor}"></span>')
    if tag == "PrefixC":
        args = " ".join(render_type(arg, 2) for arg in payload.get("ac_args", []))
        parts.append(f"- `{f'{name} {args}'.strip()}`")
    elif tag == "RecordC":
        parts.append(f"- `{name}`")
        parts.append(render_fields_table(payload.get("ac_fields", [])))
    elif tag == "InfixC":
        left = render_type(payload["ac_left"], 2)
        right = render_type(payload["ac_right"], 2)
        parts.append(f"- `{left} {name} {right}`")
    else:
        parts.append(f"- `{name}`")
    desc = render_doc_blocks(payload.get("ac_descr"))
    if desc:
        parts.append(desc)
    return "\n\n".join(parts)


def render_adt(adt_union: dict[str, Any]) -> str:
    if "ADTDoc" in adt_union and isinstance(adt_union["ADTDoc"], dict):
        adt = adt_union["ADTDoc"]
        name = str(adt["ad_name"])
        anchor = adt.get("ad_anchor")
        parts: list[str] = []
        if anchor:
            parts.append(f'<span id="{anchor}"></span>')
        args = " ".join(adt.get("ad_args", []))
        header = f"data {name}"
        if args:
            header = f"{header} {args}"
        parts.append(f"### `{header}`")
        desc = render_doc_blocks(adt.get("ad_descr"))
        if desc:
            parts.append(desc)
        parts.extend(render_warn_blocks(adt.get("ad_warns")))
        constrs = adt.get("ad_constrs", [])
        if constrs:
            parts.append("Constructors:")
            parts.append("\n\n".join(render_constructor(constructor) for constructor in constrs))
        instances = adt.get("ad_instances", [])
        if instances:
            parts.append("Instances:")
            parts.append("\n".join(f"- `{render_instance(instance)}`" for instance in instances))
        return "\n\n".join(parts)

    if "TypeSynDoc" in adt_union and isinstance(adt_union["TypeSynDoc"], dict):
        adt = adt_union["TypeSynDoc"]
        name = str(adt["ad_name"])
        anchor = adt.get("ad_anchor")
        rhs = render_type(adt.get("ad_rhs"))
        parts: list[str] = []
        if anchor:
            parts.append(f'<span id="{anchor}"></span>')
        parts.append(f"### `type {name} = {rhs}`")
        desc = render_doc_blocks(adt.get("ad_descr"))
        if desc:
            parts.append(desc)
        parts.extend(render_warn_blocks(adt.get("ad_warns")))
        instances = adt.get("ad_instances", [])
        if instances:
            parts.append("Instances:")
            parts.append("\n".join(f"- `{render_instance(instance)}`" for instance in instances))
        return "\n\n".join(parts)

    tag, adt = as_union(adt_union)
    name = str(adt["ad_name"])
    anchor = adt.get("ad_anchor")
    parts: list[str] = []
    if anchor:
        parts.append(f'<span id="{anchor}"></span>')
    if tag in {"Data", "Newtype", "Template", "Interface"}:
        args = " ".join(adt.get("ad_args", []))
        header = f"{'newtype' if tag == 'Newtype' else 'data'} {name}"
        if args:
            header = f"{header} {args}"
        parts.append(f"### `{header}`")
        desc = render_doc_blocks(adt.get("ad_descr"))
        if desc:
            parts.append(desc)
        constrs = adt.get("ad_constrs", [])
        if constrs:
            parts.append("Constructors:")
            parts.append("\n\n".join(render_constructor(constructor) for constructor in constrs))
    elif tag == "Synonym":
        rhs = render_type(adt["ad_rhs"])
        parts.append(f"### `type {name} = {rhs}`")
        desc = render_doc_blocks(adt.get("ad_descr"))
        if desc:
            parts.append(desc)
    else:
        parts.append(f"### `{name}`")
        parts.append(f"```json\n{json.dumps(adt_union, indent=2)}\n```")

    instances = adt.get("ad_instances", [])
    if instances:
        parts.append("Instances:")
        parts.append("\n".join(f"- `{render_instance(instance)}`" for instance in instances))
    return "\n\n".join(parts)


def module_file_name(module_name: str) -> str:
    return f"{slugify(module_name)}.mdx"


def normalize_link_prefix(link_prefix: str) -> str:
    trimmed = link_prefix.strip()
    if not trimmed:
        raise ValueError("link_prefix must not be empty")
    return "/" + trimmed.strip("/")


def module_template_context(
    module_doc: dict[str, Any],
    *,
    module_deprecation_introduced_in: str | None,
    module_lifecycle: dict[str, str | None] | None,
) -> dict[str, Any]:
    name = str(module_doc["md_name"])
    display_name = module_display_name(name)
    anchor = module_doc.get("md_anchor")
    descr = render_doc_blocks(module_doc.get("md_descr"))

    module_warnings = extract_tagged_warning_messages(module_doc.get("md_warn"), "WarnData")
    module_deprecations = extract_tagged_warning_messages(module_doc.get("md_warn"), "DeprecatedData")
    module_alpha_warning = next((msg for msg in module_warnings if "alpha" in msg.lower()), None)
    module_deprecation_warning = module_deprecations[0] if module_deprecations else None
    replacement_target = extract_exact_replacement_target(module_deprecations)

    module_status = "active"
    introduced_in = "-"
    removed_in = "-"
    if module_lifecycle:
        raw_status = str(module_lifecycle.get("status", "active")).strip().lower()
        if raw_status:
            module_status = raw_status
        raw_introduced = module_lifecycle.get("introduced_in")
        if isinstance(raw_introduced, str) and raw_introduced.strip():
            introduced_in = raw_introduced.strip()
        raw_removed = module_lifecycle.get("removed_in")
        if isinstance(raw_removed, str) and raw_removed.strip():
            removed_in = raw_removed.strip()

    lifecycle = "Stable."
    if module_status == "removed":
        lifecycle = "Removed."
    elif module_alpha_warning:
        lifecycle = "Alpha (experimental)."
    elif module_deprecation_warning:
        lifecycle = "Deprecated."
    elif module_warnings:
        lifecycle = "Warning."

    deprecation_since_line = "Deprecated since: `-`"
    if module_deprecations and module_deprecation_introduced_in:
        deprecation_since_line = f"Deprecated since: `{module_deprecation_introduced_in}`"

    primary_warning = ""
    if module_status == "removed":
        primary_warning = (
            f"This module was removed in `{removed_in}` and is shown here for historical reference."
            if removed_in != "-"
            else "This module is removed and is shown here for historical reference."
        )
    elif module_alpha_warning:
        primary_warning = module_alpha_warning
    elif module_deprecation_warning:
        primary_warning = module_deprecation_warning

    sections: list[dict[str, Any]] = []
    if module_doc.get("md_adts"):
        sections.append({"title": "Data Types", "bodies": [render_adt(item) for item in module_doc["md_adts"]]})
    if module_doc.get("md_classes"):
        sections.append({"title": "Typeclasses", "bodies": [render_class(item) for item in module_doc["md_classes"]]})
    if module_doc.get("md_functions"):
        sections.append({"title": "Functions", "bodies": [render_function(item) for item in module_doc["md_functions"]]})
    if module_doc.get("md_interfaces"):
        sections.append({"title": "Interfaces", "bodies": [render_interface(item) for item in module_doc["md_interfaces"]]})
    if module_doc.get("md_templates"):
        sections.append({"title": "Templates", "bodies": [render_template_doc(item) for item in module_doc["md_templates"]]})

    orphan_instances = [item for item in module_doc.get("md_instances", []) if item.get("id_isOrphan")]
    if orphan_instances:
        sections.append({"title": "Orphan Typeclass Instances", "bodies": [f"- `{render_instance(item)}`" for item in orphan_instances]})

    notice_lines = [
        f"Status: `{module_status}`",
        f"Introduced in: `{introduced_in}`",
        f"Removed in: `{removed_in}`",
        f"Warnings: `{len(module_warnings)}`",
        f"Deprecations: `{len(module_deprecations)}`",
        deprecation_since_line,
    ]
    if replacement_target:
        notice_lines.append(f"Replaces: `{replacement_target}`")

    return {
        "anchor_id": str(anchor) if anchor else "",
        "module_title": display_name,
        "module_description": descr,
        "snapshot_cards": [
            {"title": "Lifecycle", "body": lifecycle},
            {
                "title": "Notices",
                "body": "\n".join(notice_lines),
            },
        ],
        "primary_warning": primary_warning,
        "warning_items": module_warnings,
        "deprecation_items": module_deprecations,
        "sections": sections,
    }


def render_module_body(
    module_doc: dict[str, Any],
    *,
    module_deprecation_introduced_in: str | None,
    module_lifecycle: dict[str, str | None] | None,
) -> str:
    return render_template(
        "daml_json/module.md.j2",
        **module_template_context(
            module_doc,
            module_deprecation_introduced_in=module_deprecation_introduced_in,
            module_lifecycle=module_lifecycle,
        ),
    )


def module_lifecycle_badges(
    *,
    lifecycle: dict[str, str | None],
    deprecation_version: str | None,
) -> list[ReferenceBadge]:
    badges = [ReferenceBadge(f"Since {lifecycle.get('introduced_in') or '-'}", tone="added")]
    if deprecation_version:
        badges.append(ReferenceBadge(f"Deprecated {deprecation_version}", tone="removed"))
    removed_in = lifecycle.get("removed_in")
    if removed_in:
        badges.append(ReferenceBadge(f"Removed {removed_in}", tone="removed"))
    return badges


def strip_raw_markdown_trailing_whitespace(page: Page) -> Page:
    return Page(
        path=page.path,
        title=page.title,
        description=page.description,
        blocks=[
            RawMarkdown("\n".join(line.rstrip() for line in block.text.splitlines()))
            if isinstance(block, RawMarkdown)
            else block
            for block in page.blocks
        ],
    )


def build_pages(
    report: DamlDocsReport,
    *,
    output_dir: Path,
    overview_title: str = "Daml Standard Library",
    link_prefix: str | None = None,
) -> tuple[Path, list[Page]]:
    root = output_dir.parent
    pages: list[Page] = []
    module_entries: list[tuple[str, str, str]] = []
    module_cards: list[ReferenceCard] = []
    normalized_link_prefix = normalize_link_prefix(link_prefix) if link_prefix else None
    modules_sorted = sorted(
        report.modules,
        key=lambda module: module_display_name(str(module.get("md_name", ""))).lower(),
    )
    modules_by_name = {str(module.get("md_name", "")): module for module in modules_sorted}

    for module in modules_sorted:
        name = str(module["md_name"])
        if name in EXCLUDED_MODULE_NAMES:
            continue
        display_name = module_display_name(name)
        target = output_dir / module_file_name(name)
        target_ref = module_file_name(name).removesuffix(".mdx")
        module_entries.append((name, display_name, target_ref))
        pages.append(
            markdown_page(
                path=target.relative_to(root).as_posix(),
                title=display_name,
                description=f"Reference documentation for Daml module {display_name}.",
                template_name="daml_json/module.md.j2",
                **module_template_context(
                    module,
                    module_deprecation_introduced_in=report.module_deprecation_first_seen.get(name),
                    module_lifecycle=report.module_lifecycle.get(name),
                ),
            )
        )

    for source_name, display_name, target in module_entries:
        lifecycle = report.module_lifecycle.get(source_name, {})
        deprecation_version = report.module_deprecation_first_seen.get(source_name)
        if normalized_link_prefix:
            module_link = f"{normalized_link_prefix}/{target}"
        else:
            module_link = (output_dir / target).relative_to(root).with_suffix("").as_posix()
        module_doc = modules_by_name[source_name]
        module_cards.append(
            ReferenceCard(
                title=display_name,
                href=module_link,
                summary=module_summary_preview(module_doc),
                badges=module_lifecycle_badges(
                    lifecycle=lifecycle,
                    deprecation_version=deprecation_version,
                ),
                meta_items=[
                    ReferenceMetaItem("Kind", "Module"),
                    ReferenceMetaItem("Introduced", lifecycle.get("introduced_in") or "-"),
                    ReferenceMetaItem("Changed", "-"),
                    ReferenceMetaItem("Deprecated", deprecation_version or "-"),
                    ReferenceMetaItem("Removed", lifecycle.get("removed_in") or "-"),
                ],
            )
        )
    version_cards = [
        ReferenceCard(
            title=version,
            summary="Module changes included in this Daml docs JSON snapshot.",
            badges=[
                ReferenceBadge(
                    f"Added {sum(1 for lifecycle in report.module_lifecycle.values() if lifecycle.get('introduced_in') == version)}",
                    tone="added",
                ),
                ReferenceBadge("Changed 0", tone="changed"),
                ReferenceBadge(
                    f"Removed {sum(1 for lifecycle in report.module_lifecycle.values() if lifecycle.get('removed_in') == version)}",
                    tone="removed",
                ),
            ],
        )
        for version in report.versions
    ]

    pages.insert(
        0,
        strip_raw_markdown_trailing_whitespace(
            render_collection_page(
                ReferenceCollectionPage(
                    path=(output_dir / "index.mdx").relative_to(root).as_posix(),
                    title=overview_title,
                    description=f"Reference documentation for {overview_title} modules.",
                    eyebrow="Daml Reference",
                    summary=f"Generated module overview for {overview_title}, built from versioned docs JSON snapshots.",
                    badges=[ReferenceBadge("Daml", tone="protocol"), ReferenceBadge(report.publish_version, tone="neutral")],
                    meta_items=[
                        ReferenceMetaItem("Publish version", report.publish_version),
                        ReferenceMetaItem("Source", report.source_name),
                        ReferenceMetaItem("Version filter", report.version_filter),
                    ],
                    sections=[
                        ReferenceSection(
                            heading="Modules",
                            body_markdown=safe_markdown_text(
                                "Open a module page for declarations, type signatures, warnings, and lifecycle details."
                            ),
                            cards=module_cards,
                        ),
                        ReferenceSection(
                            heading="Version Summary",
                            cards=version_cards,
                        ),
                    ],
                )
            )
        ),
    )
    return root, pages
