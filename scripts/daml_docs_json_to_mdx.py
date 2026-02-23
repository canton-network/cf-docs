#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Convert damlc docs JSON output into MDX files and optionally update docs.json navigation."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

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


def as_union(node: dict[str, Any]) -> tuple[str, Any]:
    if len(node) != 1:
        raise ValueError(f"Expected tagged union object, got keys={list(node.keys())}")
    [(tag, payload)] = node.items()
    return tag, payload


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def escape_md_cell(text: str) -> str:
    return text.replace("|", r"\|").replace("\n", "<br/>")


def render_doc_blocks(descr: Any) -> str:
    if not descr:
        return ""
    blocks: list[str] = []
    for paragraph in descr:
        if isinstance(paragraph, list):
            raw = "\n".join(str(x) for x in paragraph).strip()
        else:
            raw = str(paragraph).strip()
        if raw:
            blocks.append(raw)
    return "\n\n".join(blocks)


def module_display_name(module_name: str) -> str:
    parts = [part for part in module_name.split(".") if part]
    if not parts:
        return module_name
    normalized: list[str] = []
    for part in parts:
        mapped = ACRONYM_PARTS.get(part.lower())
        if mapped:
            normalized.append(mapped)
            continue
        if part.isupper():
            normalized.append(part)
        elif part.islower():
            normalized.append(part.capitalize())
        else:
            normalized.append(part)
    return " ".join(normalized)


def render_type(ty: Any, prec: int = 0) -> str:
    if not isinstance(ty, dict):
        return str(ty)
    tag, payload = as_union(ty)
    if tag == "TypeApp":
        _ref, name, args = payload
        base = str(name)
        rendered_args = [render_type(arg, 2) for arg in args]
        text = " ".join([base] + rendered_args).strip()
        return f"({text})" if prec >= 2 and args else text
    if tag == "TypeFun":
        parts = [render_type(p, 1) for p in payload]
        text = " -> ".join(parts)
        return f"({text})" if prec >= 1 else text
    if tag == "TypeList":
        return f"[{render_type(payload, 0)}]"
    if tag == "TypeTuple":
        items = [render_type(p, 0) for p in payload]
        if len(items) == 1:
            return items[0]
        return f"({', '.join(items)})"
    if tag == "TypeLit":
        return str(payload)
    return str(ty)


def render_context(ctx: list[Any]) -> str:
    if not ctx:
        return ""
    items = [render_type(t, 0) for t in ctx]
    if len(items) == 1:
        return f"{items[0]} => "
    return f"({', '.join(items)}) => "


def render_fields_table(fields: list[dict[str, Any]]) -> str:
    if not fields:
        return "(no fields)"
    rows = [
        "| Field | Type | Description |",
        "| :---- | :--- | :---------- |",
    ]
    for field in fields:
        name = str(field["fd_name"])
        ty = render_type(field["fd_type"])
        doc = render_doc_blocks(field.get("fd_descr"))
        rows.append(
            f"| {escape_md_cell(name)} | {escape_md_cell(ty)} | {escape_md_cell(doc)} |"
        )
    return "\n".join(rows)


def render_instance(inst: dict[str, Any]) -> str:
    return f"instance {render_context(inst.get('id_context', []))}{render_type(inst['id_type'])}"


def render_function(fn: dict[str, Any]) -> str:
    name = str(fn["fct_name"])
    anchor = fn.get("fct_anchor")
    parts: list[str] = []
    if anchor:
        parts.append(f'<a id="{anchor}"></a>')
    parts.append(f"### `{name}`")
    signature = f"{name} : {render_context(fn.get('fct_context', []))}{render_type(fn['fct_type'])}"
    parts.append(f"```daml\n{signature}\n```")
    desc = render_doc_blocks(fn.get("fct_descr"))
    if desc:
        parts.append(desc)
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
    ctx = render_context(cls.get("cl_super", []))
    header = f"class {ctx}{name}"
    if args:
        header = f"{header} {args}"
    parts: list[str] = []
    if anchor:
        parts.append(f'<a id="{anchor}"></a>')
    parts.append(f"### `{header}`")
    desc = render_doc_blocks(cls.get("cl_descr"))
    if desc:
        parts.append(desc)
    methods = cls.get("cl_methods", [])
    if methods:
        parts.append("Methods:")
        parts.append("\n".join(render_class_method(m) for m in methods))
    instances = cls.get("cl_instances", [])
    if instances:
        parts.append("Instances:")
        parts.append("\n".join(f"- `{render_instance(i)}`" for i in instances))
    return "\n\n".join(parts)


def render_constructor(constructor: dict[str, Any]) -> str:
    tag, c = as_union(constructor)
    name = str(c["ac_name"])
    anchor = c.get("ac_anchor")
    parts: list[str] = []
    if anchor:
        parts.append(f'<a id="{anchor}"></a>')
    if tag == "PrefixC":
        args = " ".join(render_type(arg, 2) for arg in c.get("ac_args", []))
        sig = f"{name} {args}".strip()
        parts.append(f"- `{sig}`")
    elif tag == "RecordC":
        parts.append(f"- `{name}`")
        parts.append("")
        parts.append(render_fields_table(c.get("ac_fields", [])))
    else:
        parts.append(f"- `{name}`")
    desc = render_doc_blocks(c.get("ac_descr"))
    if desc:
        parts.append(f"  {desc.replace(chr(10), chr(10) + '  ')}")
    return "\n".join(parts)


def render_adt(adt_union: dict[str, Any]) -> str:
    tag, adt = as_union(adt_union)
    name = str(adt["ad_name"])
    anchor = adt.get("ad_anchor")
    args = " ".join(adt.get("ad_args", []))
    parts: list[str] = []
    if anchor:
        parts.append(f'<a id="{anchor}"></a>')
    if tag == "TypeSynDoc":
        rhs = render_type(adt["ad_rhs"])
        title = f"type {name}"
        if args:
            title = f"{title} {args}"
        title = f"{title} = {rhs}"
    else:
        title = f"data {name}"
        if args:
            title = f"{title} {args}"
    parts.append(f"### `{title}`")
    desc = render_doc_blocks(adt.get("ad_descr"))
    if desc:
        parts.append(desc)
    constrs = adt.get("ad_constrs", [])
    if constrs:
        parts.append("Constructors:")
        parts.append("\n".join(render_constructor(c) for c in constrs))
    instances = adt.get("ad_instances", [])
    if instances:
        parts.append("Instances:")
        parts.append("\n".join(f"- `{render_instance(i)}`" for i in instances))
    return "\n\n".join(parts)


def render_module(module_doc: dict[str, Any]) -> str:
    name = str(module_doc["md_name"])
    display_name = module_display_name(name)
    anchor = module_doc.get("md_anchor")
    parts: list[str] = []
    if anchor:
        parts.append(f'<a id="{anchor}"></a>')
    parts.append(f"# {display_name}")
    descr = render_doc_blocks(module_doc.get("md_descr"))
    if descr:
        parts.append(descr)

    sections: list[tuple[str, list[str]]] = []
    adts = module_doc.get("md_adts", [])
    if adts:
        sections.append(("Data Types", [render_adt(a) for a in adts]))
    classes = module_doc.get("md_classes", [])
    if classes:
        sections.append(("Typeclasses", [render_class(c) for c in classes]))
    functions = module_doc.get("md_functions", [])
    if functions:
        sections.append(("Functions", [render_function(f) for f in functions]))
    interfaces = module_doc.get("md_interfaces", [])
    if interfaces:
        sections.append(("Interfaces", [f"```json\n{json.dumps(i, indent=2)}\n```" for i in interfaces]))
    templates = module_doc.get("md_templates", [])
    if templates:
        sections.append(("Templates", [f"```json\n{json.dumps(t, indent=2)}\n```" for t in templates]))

    orphan_instances = [i for i in module_doc.get("md_instances", []) if i.get("id_isOrphan")]
    if orphan_instances:
        sections.append(
            ("Orphan Typeclass Instances", [f"- `{render_instance(i)}`" for i in orphan_instances])
        )

    for section_name, bodies in sections:
        parts.append(f"## {section_name}")
        parts.append("\n\n".join(bodies))

    return "\n\n".join(parts).rstrip() + "\n"


def module_file_name(module_name: str) -> str:
    return f"{slugify(module_name)}.mdx"


def load_modules(input_json: Path) -> list[dict[str, Any]]:
    with input_json.open("r", encoding="utf-8") as f:
        modules = json.load(f)
    if isinstance(modules, dict):
        modules = [modules]
    if not isinstance(modules, list):
        raise ValueError("Expected top-level JSON array (or object) of modules")
    return modules


def write_modules(modules: list[dict[str, Any]], out_dir: Path, index_file: str = "index.mdx") -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old_mdx in out_dir.glob("*.mdx"):
        old_mdx.unlink()

    module_targets: list[str] = []
    module_names: list[str] = []
    for module in modules:
        name = str(module["md_name"])
        if name in EXCLUDED_MODULE_NAMES:
            continue
        module_names.append(module_display_name(name))
        target = module_file_name(name).removesuffix(".mdx")
        module_targets.append(target)
        text = render_module(module)
        (out_dir / f"{target}.mdx").write_text(text, encoding="utf-8")

    index_target = Path(index_file).stem
    index_lines = [
        "# Generated Daml API Reference",
        "",
        "## Modules",
        "",
    ]
    for name, target in zip(module_names, module_targets):
        index_lines.append(f"- [{name}](./{target})")
    (out_dir / index_file).write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")
    return [index_target] + module_targets


def update_docs_json_navigation(
    docs_json_path: Path,
    nav_group_name: str,
    nav_pages: list[str],
    create_nav_group_if_missing: bool = False,
    nav_dropdown_name: str | None = None,
) -> int:
    with docs_json_path.open("r", encoding="utf-8") as f:
        docs_json = json.load(f)

    replacements = 0

    if nav_dropdown_name:
        def walk_dropdowns(node: Any) -> None:
            nonlocal replacements
            if isinstance(node, dict):
                if node.get("dropdown") == nav_dropdown_name and isinstance(node.get("versions"), list):
                    for version in node["versions"]:
                        if not isinstance(version, dict):
                            continue
                        groups = version.get("groups")
                        if not isinstance(groups, list):
                            continue
                        found = False
                        for group in groups:
                            if isinstance(group, dict) and group.get("group") == nav_group_name:
                                group["pages"] = nav_pages
                                replacements += 1
                                found = True
                                break
                        if not found and create_nav_group_if_missing:
                            insert_at = len(groups)
                            for i, group in enumerate(groups):
                                if isinstance(group, dict) and group.get("group") == "Help":
                                    insert_at = i
                                    break
                            groups.insert(insert_at, {"group": nav_group_name, "pages": nav_pages})
                            replacements += 1
                for value in node.values():
                    walk_dropdowns(value)
            elif isinstance(node, list):
                for item in node:
                    walk_dropdowns(item)

        walk_dropdowns(docs_json)
    else:
        def walk(node: Any) -> None:
            nonlocal replacements
            if isinstance(node, dict):
                if node.get("group") == nav_group_name and isinstance(node.get("pages"), list):
                    node["pages"] = nav_pages
                    replacements += 1
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(docs_json)

    if replacements == 0:
        if create_nav_group_if_missing and not nav_dropdown_name:
            raise ValueError(
                "create_nav_group_if_missing requires nav_dropdown_name to scope where new groups are inserted"
            )
        if nav_dropdown_name:
            raise ValueError(
                f"Did not update group '{nav_group_name}' under dropdown '{nav_dropdown_name}' in {docs_json_path}"
            )
        raise ValueError(f"Did not find group '{nav_group_name}' in {docs_json_path}")

    with docs_json_path.open("w", encoding="utf-8") as f:
        json.dump(docs_json, f, indent=2)
        f.write("\n")
    return replacements


def build_nav_pages(nav_base: str, module_targets: list[str]) -> list[str]:
    nav_base = nav_base.strip("/")
    return [f"{nav_base}/{target}" for target in module_targets]


def get_navigation_dropdowns(docs_json: dict[str, Any], docs_json_path: Path) -> list[Any]:
    navigation = docs_json.get("navigation")
    if isinstance(navigation, list):
        return navigation
    if isinstance(navigation, dict):
        dropdowns = navigation.get("dropdowns")
        if isinstance(dropdowns, list):
            return dropdowns
    raise ValueError(
        f"Expected docs.json 'navigation' to be a list or an object with 'dropdowns' list in {docs_json_path}"
    )


def update_daml_reference_docs_navigation(
    docs_json_path: Path,
    version_entries: list[dict[str, Any]],
    dropdown_name: str = "Daml Reference Docs",
    group_name: str = "Daml Prim API",
    icon: str = "book-open",
    remove_legacy_dropdown_name: str = "App Development",
    remove_legacy_group_name: str = "Generated API Reference",
) -> tuple[int, bool]:
    with docs_json_path.open("r", encoding="utf-8") as f:
        docs_json = json.load(f)

    navigation = get_navigation_dropdowns(docs_json, docs_json_path)

    normalized_versions: list[dict[str, Any]] = []
    for entry in version_entries:
        version = str(entry.get("version", "")).strip()
        pages = entry.get("pages")
        if not version:
            raise ValueError("Each version entry must include a non-empty 'version'")
        if not isinstance(pages, list) or not pages or not all(isinstance(p, str) for p in pages):
            raise ValueError(f"Version '{version}' must define a non-empty string list in 'pages'")
        normalized_versions.append(
            {
                "version": version,
                "groups": [
                    {
                        "group": group_name,
                        "pages": pages,
                    }
                ],
            }
        )

    removed_legacy_groups = 0
    for section in navigation:
        if not isinstance(section, dict):
            continue
        if section.get("dropdown") != remove_legacy_dropdown_name:
            continue
        versions = section.get("versions")
        if not isinstance(versions, list):
            continue
        for version in versions:
            if not isinstance(version, dict):
                continue
            groups = version.get("groups")
            if not isinstance(groups, list):
                continue
            before = len(groups)
            version["groups"] = [
                g
                for g in groups
                if not (isinstance(g, dict) and g.get("group") == remove_legacy_group_name)
            ]
            removed_legacy_groups += before - len(version["groups"])

    dropdown_indices = [
        i
        for i, section in enumerate(navigation)
        if isinstance(section, dict) and section.get("dropdown") == dropdown_name
    ]
    updated_existing = len(dropdown_indices) > 0

    if updated_existing:
        keep = dropdown_indices[0]
        dropdown = navigation[keep]
        if isinstance(dropdown, dict):
            dropdown["icon"] = icon
            dropdown["versions"] = normalized_versions
        for idx in reversed(dropdown_indices[1:]):
            del navigation[idx]
    else:
        insert_at = len(navigation)
        for i, section in enumerate(navigation):
            if isinstance(section, dict) and section.get("dropdown") == remove_legacy_dropdown_name:
                insert_at = i + 1
                break
        navigation.insert(
            insert_at,
            {
                "dropdown": dropdown_name,
                "icon": icon,
                "versions": normalized_versions,
            },
        )

    with docs_json_path.open("w", encoding="utf-8") as f:
        json.dump(docs_json, f, indent=2)
        f.write("\n")

    return removed_legacy_groups, updated_existing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, required=True, help="Path to damlc docs JSON file")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to write .mdx files into")
    parser.add_argument("--index-file", default="index.mdx", help="Index file name (default: index.mdx)")
    parser.add_argument("--docs-json", type=Path, help="Path to docs.json to update navigation")
    parser.add_argument(
        "--nav-group-name",
        default="Generated API Reference",
        help="Group name in docs.json whose pages should be replaced",
    )
    parser.add_argument(
        "--nav-base",
        help="Page path prefix used in docs.json (defaults to output-dir relative to docs.json parent)",
    )
    parser.add_argument(
        "--create-nav-group-if-missing",
        action="store_true",
        help="Insert nav group when missing (requires --nav-dropdown-name)",
    )
    parser.add_argument(
        "--nav-dropdown-name",
        help="Limit docs.json updates to versions under this dropdown (for example: Application Development)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    modules = load_modules(args.input_json)
    module_targets = write_modules(modules, args.output_dir, index_file=args.index_file)

    nav_updates = 0
    if args.docs_json:
        nav_base = args.nav_base
        if not nav_base:
            nav_base = Path(os.path.relpath(args.output_dir, args.docs_json.parent)).as_posix()
        nav_pages = build_nav_pages(nav_base, module_targets)
        nav_updates = update_docs_json_navigation(
            docs_json_path=args.docs_json,
            nav_group_name=args.nav_group_name,
            nav_pages=nav_pages,
            create_nav_group_if_missing=args.create_nav_group_if_missing,
            nav_dropdown_name=args.nav_dropdown_name,
        )

    print(f"Wrote {len(module_targets) - 1} module files + {args.index_file} into {args.output_dir}")
    if args.docs_json:
        print(f"Updated {nav_updates} '{args.nav_group_name}' group(s) in {args.docs_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
