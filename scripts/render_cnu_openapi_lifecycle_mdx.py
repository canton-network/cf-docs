#!/usr/bin/env python3
"""
Render CNU OpenAPI lifecycle JSON into Mintlify-compatible MDX pages
and optionally update docs.json navigation.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


def slugify(value: str) -> str:
    out = value.lower()
    out = re.sub(r"[^a-z0-9]+", "-", out)
    out = re.sub(r"-{2,}", "-", out).strip("-")
    return out


def md_text(text: Any) -> str:
    out = html.escape(str(text), quote=False)
    out = out.replace("{", "&#123;").replace("}", "&#125;")
    out = out.replace("|", "\\|").replace("\n", " ").strip()
    return out


def md_code(text: Any) -> str:
    out = str(text).replace("`", "\\`")
    out = out.replace("|", "\\|").replace("\n", " ").strip()
    return out


def route_for_path(path: Path) -> str:
    s = path.as_posix()
    if s.endswith(".mdx"):
        s = s[:-4]
    return f"/{s}"


def docs_json_page_ref(path: Path) -> str:
    s = path.as_posix()
    if s.endswith(".mdx"):
        s = s[:-4]
    return s


def lifecycle_value(value: str | None, kind: str) -> str:
    if not value:
        return "-"
    rendered = f"`{md_code(value)}`"
    if kind == "removed":
        return f"❌ {rendered}"
    return rendered


def changed_versions_value(changed: List[str]) -> str:
    if not changed:
        return "-"
    if len(changed) <= 5:
        return "`" + md_code(", ".join(changed)) + "`"
    head = ", ".join(changed[:5])
    return "`" + md_code(f"{head} (+{len(changed) - 5} more)") + "`"


def lifecycle_counts(spec: Dict[str, Any]) -> Dict[str, int]:
    records = spec.get("entity_lifecycle", [])
    return {
        "total": len(records),
        "changed": sum(1 for r in records if r.get("changed_in_versions")),
        "removed": sum(1 for r in records if r.get("removed_version")),
        "introduced_later": sum(
            1 for r in records if r.get("introduced_version") != spec.get("introduced_version")
        ),
    }


def interesting_entities(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    baseline = spec.get("introduced_version")
    rows = []
    for rec in spec.get("entity_lifecycle", []):
        if (
            rec.get("introduced_version") != baseline
            or rec.get("changed_in_versions")
            or rec.get("removed_version")
        ):
            rows.append(rec)
    rows.sort(key=lambda r: (r.get("entity_type", ""), r.get("name", "")))
    return rows


def endpoint_header(op: Dict[str, Any]) -> str:
    method = str(op.get("method", "")).upper()
    path = str(op.get("path", ""))
    return f"`{md_code(method)} {md_code(path)}`"


def render_endpoint_reference(ops: List[Dict[str, Any]], max_endpoints: int) -> List[str]:
    lines: List[str] = ["## Endpoint Reference (Latest)", ""]
    if not ops:
        lines.extend(["No endpoint details available in latest spec.", ""])
        return lines

    shown = ops[:max_endpoints]
    lines.extend(
        [
            "| Endpoint | Operation ID | Summary | Tags |",
            "| --- | --- | --- | --- |",
        ]
    )
    for op in shown:
        op_id = op.get("operation_id") or "-"
        summary = op.get("summary") or "-"
        tags = ", ".join(op.get("tags") or [])
        tags = tags if tags else "-"
        lines.append(
            f"| {endpoint_header(op)} | `{md_code(op_id)}` | {md_text(summary)} | `{md_code(tags)}` |"
        )

    if len(ops) > max_endpoints:
        lines.extend(
            [
                "",
                f"_Showing first {max_endpoints} endpoints out of {len(ops)}._",
                "",
            ]
        )
        return lines

    lines.append("")
    for op in shown:
        lines.extend(
            [
                f"### {endpoint_header(op)}",
                "",
            ]
        )
        if op.get("operation_id"):
            lines.append(f"- Operation ID: `{md_code(op['operation_id'])}`")
        if op.get("summary"):
            lines.append(f"- Summary: {md_text(op['summary'])}")
        if op.get("description"):
            lines.append(f"- Description: {md_text(op['description'])}")
        if op.get("tags"):
            lines.append(f"- Tags: `{md_code(', '.join(op['tags']))}`")
        lines.append("")

        params = op.get("parameters", [])
        if params:
            lines.extend(
                [
                    "**Parameters**",
                    "",
                    "| Name | In | Required | Schema | Description |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for p in params:
                lines.append(
                    f"| `{md_code(p.get('name', '-'))}` | `{md_code(p.get('in', '-'))}` | `{md_code('yes' if p.get('required') else 'no')}` | `{md_code(p.get('schema', '-'))}` | {md_text(p.get('description', '-') or '-')} |"
                )
            lines.append("")

        req = op.get("request_body", {})
        if req:
            cts = req.get("content_types", [])
            schemas = req.get("schema_by_content_type", {})
            lines.append("**Request Body**")
            lines.append("")
            lines.append(f"- Required: `{md_code('yes' if req.get('required') else 'no')}`")
            if cts:
                lines.append("- Content:")
                for ct in cts:
                    lines.append(f"  - `{md_code(ct)}` -> `{md_code(schemas.get(ct, '-'))}`")
            else:
                lines.append("- Content: `-`")
            lines.append("")

        responses = op.get("responses", [])
        if responses:
            lines.extend(
                [
                    "**Responses**",
                    "",
                    "| Code | Description | Content Types | Schemas |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for r in responses:
                cts = r.get("content_types", [])
                schemas = r.get("schema_by_content_type", {})
                ct_val = ", ".join(cts) if cts else "-"
                schema_val = ", ".join(f"{k}:{schemas.get(k, '-')}" for k in cts) if cts else "-"
                lines.append(
                    f"| `{md_code(r.get('code', '-'))}` | {md_text(r.get('description', '-') or '-')} | `{md_code(ct_val)}` | `{md_code(schema_val)}` |"
                )
            lines.append("")

    return lines


def spec_page_sections(
    spec: Dict[str, Any],
    max_changed: int,
    max_ops: int,
    max_components: int,
    max_endpoints: int,
) -> List[str]:
    lines: List[str] = []
    title = spec.get("display_name") or spec["spec_id"]
    counts = lifecycle_counts(spec)

    latest_ops = spec.get("latest_entities", {}).get("operations", [])
    latest_paths = spec.get("latest_entities", {}).get("paths", [])
    latest_components = spec.get("latest_entities", {}).get("components", [])
    latest_tags = spec.get("latest_entities", {}).get("tags", [])
    interesting = interesting_entities(spec)

    lines.extend(
        [
            "---",
            f"title: \"{md_text(title)}\"",
            "description: \"Generated lifecycle view for a CNU OpenAPI specification\"",
            "---",
            "",
            "Generated from release tags in `canton-network-utilities`.",
            "",
            "## Spec Metadata",
            "",
            f"- Canonical spec id: `{md_code(spec['spec_id'])}`",
            f"- Latest git path: `{md_code(spec.get('latest_git_path', '-'))}`",
            f"- OpenAPI version (latest): `{md_code(spec.get('latest_openapi_version', '-'))}`",
            f"- Info version (latest): `{md_code(spec.get('latest_info_version', '-'))}`",
            f"- Introduced: {lifecycle_value(spec.get('introduced_version'), 'introduced')}",
            f"- Changed in versions: {changed_versions_value(spec.get('changed_in_versions', []))}",
            f"- Removed: {lifecycle_value(spec.get('removed_version'), 'removed')}",
            "",
            "## Entity Summary",
            "",
            f"- Total entities tracked: `{counts['total']}`",
            f"- Entities introduced after spec introduction: `{counts['introduced_later']}`",
            f"- Entities changed at least once: `{counts['changed']}`",
            f"- Entities removed: `{counts['removed']}`",
            f"- Latest operations: `{len(latest_ops)}`",
            f"- Latest paths: `{len(latest_paths)}`",
            f"- Latest components: `{len(latest_components)}`",
            f"- Latest tags: `{len(latest_tags)}`",
            "",
        ]
    )

    lines.extend(render_endpoint_reference(spec.get("latest_operation_details", []), max_endpoints))

    lines.extend(
        [
            "## Version Change Timeline",
            "",
            "| Version | Added | Changed | Removed |",
            "| --- | --- | --- | --- |",
        ]
    )

    for version in spec.get("versions_present", []):
        delta = spec.get("per_version_entity_deltas", {}).get(version, {})
        lines.append(
            f"| `{md_code(version)}` | `{delta.get('added_count', 0)}` | `{delta.get('changed_count', 0)}` | `{delta.get('removed_count', 0)}` |"
        )

    lines.extend(["", "## Changed Entities", ""])
    if not interesting:
        lines.extend(["No entity-level lifecycle changes in the selected version range.", ""])
    else:
        lines.extend(
            [
                "| Entity | Type | Introduced | Changed In | Removed |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for rec in interesting[:max_changed]:
            lines.append(
                f"| `{md_code(rec.get('name', ''))}` | `{md_code(rec.get('entity_type', ''))}` | {lifecycle_value(rec.get('introduced_version'), 'introduced')} | {changed_versions_value(rec.get('changed_in_versions', []))} | {lifecycle_value(rec.get('removed_version'), 'removed')} |"
            )
        if len(interesting) > max_changed:
            lines.extend(
                [
                    "",
                    f"_Showing first {max_changed} rows out of {len(interesting)} changed entities._",
                ]
            )
        lines.append("")

    lines.extend(["## Latest Operations", ""])
    if not latest_ops:
        lines.extend(["No operations in latest version.", ""])
    else:
        lines.extend(
            [
                "| Operation | Introduced | Changed In | Removed |",
                "| --- | --- | --- | --- |",
            ]
        )
        for rec in latest_ops[:max_ops]:
            lines.append(
                f"| `{md_code(rec.get('name', ''))}` | {lifecycle_value(rec.get('introduced_version'), 'introduced')} | {changed_versions_value(rec.get('changed_in_versions', []))} | {lifecycle_value(rec.get('removed_version'), 'removed')} |"
            )
        if len(latest_ops) > max_ops:
            lines.extend(
                [
                    "",
                    f"_Showing first {max_ops} operations out of {len(latest_ops)}._",
                ]
            )
        lines.append("")

    lines.extend(["## Latest Components", ""])
    if not latest_components:
        lines.extend(["No components in latest version.", ""])
    else:
        lines.extend(
            [
                "| Component | Introduced | Changed In | Removed |",
                "| --- | --- | --- | --- |",
            ]
        )
        for rec in latest_components[:max_components]:
            lines.append(
                f"| `{md_code(rec.get('name', ''))}` | {lifecycle_value(rec.get('introduced_version'), 'introduced')} | {changed_versions_value(rec.get('changed_in_versions', []))} | {lifecycle_value(rec.get('removed_version'), 'removed')} |"
            )
        if len(latest_components) > max_components:
            lines.extend(
                [
                    "",
                    f"_Showing first {max_components} components out of {len(latest_components)}._",
                ]
            )
        lines.append("")

    return lines


def write_spec_pages(
    payload: Dict[str, Any],
    specs_dir: Path,
    max_changed: int,
    max_ops: int,
    max_components: int,
    max_endpoints: int,
    include_spec_re: re.Pattern[str] | None,
    exclude_spec_re: re.Pattern[str] | None,
) -> List[Tuple[Dict[str, Any], Path]]:
    rows: List[Tuple[Dict[str, Any], Path]] = []
    specs_dir.mkdir(parents=True, exist_ok=True)

    specs = []
    for spec in payload.get("specs", []):
        spec_id = spec.get("spec_id", "")
        if include_spec_re and not include_spec_re.search(spec_id):
            continue
        if exclude_spec_re and exclude_spec_re.search(spec_id):
            continue
        specs.append(spec)
    specs.sort(key=lambda s: s.get("spec_id", ""))
    for spec in specs:
        slug = slugify(spec["spec_id"])
        out_path = specs_dir / f"{slug}.mdx"
        lines = spec_page_sections(
            spec,
            max_changed=max_changed,
            max_ops=max_ops,
            max_components=max_components,
            max_endpoints=max_endpoints,
        )
        out_path.write_text("\n".join(lines), encoding="utf-8")
        rows.append((spec, out_path))

    return rows


def write_overview_page(
    payload: Dict[str, Any],
    overview_path: Path,
    spec_pages: List[Tuple[Dict[str, Any], Path]],
) -> None:
    lines: List[str] = []
    lines.extend(
        [
            "---",
            "title: \"Splice APIs\"",
            "description: \"Generated OpenAPI lifecycle reference for Canton Network Utilities\"",
            "---",
            "",
            "This section is generated from clean release tags in `canton-network-utilities`.",
            "",
            f"- Generated at (UTC): `{md_code(payload.get('generated_at_utc', '-'))}`",
            f"- Source repo: `{md_code(payload.get('source_repo', '-'))}`",
            f"- Tag filter: `{md_code(payload.get('tag_filter', '-'))}`",
            "",
            "## Summary",
            "",
            f"- Tags scanned: `{payload.get('summary', {}).get('tag_count', 0)}`",
            f"- Specs discovered: `{payload.get('summary', {}).get('spec_count', 0)}`",
            f"- Total entities tracked: `{payload.get('summary', {}).get('total_entities', 0)}`",
            f"- Total entity change events: `{payload.get('summary', {}).get('total_entity_change_events', 0)}`",
            "",
            "## Specs",
            "",
            "| Page | Spec | Introduced | Latest | Removed | Changed In Versions | Entities |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for spec, path in spec_pages:
        route = route_for_path(path)
        lines.append(
            f"| [Open]({route}) | `{md_code(spec['spec_id'])}` | {lifecycle_value(spec.get('introduced_version'), 'introduced')} | `{md_code(spec.get('latest_version', '-'))}` | {lifecycle_value(spec.get('removed_version'), 'removed')} | {changed_versions_value(spec.get('changed_in_versions', []))} | `{md_code(spec.get('entity_count', 0))}` |"
        )

    lines.extend(
        [
            "",
            "## Regenerate",
            "",
            "```bash",
            "cd /Users/danielporter/new-docs",
            "python3 scripts/cnu_openapi_lifecycle_mvp.py \\",
            "  --repo /Users/danielporter/canton-network-utilities \\",
            "  --output .internal/generated/cnu-openapi-lifecycle-mvp.json",
            "python3 scripts/render_cnu_openapi_lifecycle_mdx.py \\",
            "  --input .internal/generated/cnu-openapi-lifecycle-mvp.json \\",
            "  --overview docs-main/global-synchronizer/reference/splice-apis.mdx \\",
            "  --specs-dir docs-main/global-synchronizer/reference/splice-api-specs \\",
            "  --docs-json docs.json \\",
            "  --update-docs-json",
            "```",
            "",
        ]
    )

    overview_path.parent.mkdir(parents=True, exist_ok=True)
    overview_path.write_text("\n".join(lines), encoding="utf-8")


def update_docs_json(docs_json_path: Path, overview_path: Path, spec_paths: List[Path]) -> None:
    data = json.loads(docs_json_path.read_text(encoding="utf-8"))

    overview_ref = docs_json_page_ref(overview_path)
    spec_refs = [docs_json_page_ref(p) for p in spec_paths]

    reference_group = {
        "group": "Reference",
        "pages": [
            overview_ref,
            {
                "group": "Splice OpenAPI Specs",
                "pages": spec_refs,
            },
        ],
    }

    nav = data.get("navigation", {})
    dropdowns = nav.get("dropdowns", [])
    target = None
    for d in dropdowns:
        if d.get("dropdown") == "Global Synchronizer":
            target = d
            break
    if target is None:
        raise ValueError("Could not find `Global Synchronizer` dropdown in docs.json")

    def is_generated_reference_group(group: Any) -> bool:
        if not isinstance(group, dict):
            return False
        if group.get("group") != "Reference":
            return False
        pages = group.get("pages", [])
        if overview_ref in pages:
            return True
        for page in pages:
            if isinstance(page, dict) and page.get("group") == "Splice OpenAPI Specs":
                sub_pages = page.get("pages", [])
                if any(ref in sub_pages for ref in spec_refs):
                    return True
        return False

    # Remove generated OpenAPI reference group from Global Synchronizer.
    version_names: List[str] = []
    for version in target.get("versions", []):
        if version.get("version"):
            version_names.append(version["version"])
        groups = [g for g in version.get("groups", []) if not is_generated_reference_group(g)]
        version["groups"] = groups

    # Add / update a dedicated Utilities dropdown for these generated pages.
    utility_dropdowns = [d for d in dropdowns if d.get("dropdown") == "Utilities"]
    utilities = next(
        (d for d in utility_dropdowns if isinstance(d.get("groups"), list) and d.get("groups")),
        utility_dropdowns[0] if utility_dropdowns else None,
    )
    for extra in utility_dropdowns:
        if extra is not utilities:
            dropdowns.remove(extra)
    if utilities is None:
        utilities = {"dropdown": "Utilities", "versions": []}
        gs_idx = next(
            (i for i, d in enumerate(dropdowns) if d.get("dropdown") == "Global Synchronizer"),
            len(dropdowns),
        )
        dropdowns.insert(gs_idx + 1, utilities)

    # Support both docs.json shapes:
    # - versioned dropdowns: { "versions": [...] }
    # - non-versioned dropdowns: { "groups": [...] }
    if isinstance(utilities.get("groups"), list) and not utilities.get("versions"):
        groups = [g for g in utilities.get("groups", []) if not is_generated_reference_group(g)]
        help_idx = next((i for i, g in enumerate(groups) if g.get("group") == "Help"), len(groups))
        groups.insert(help_idx, reference_group)
        utilities["groups"] = groups
    else:
        utility_versions = {v.get("version"): v for v in utilities.get("versions", []) if v.get("version")}
        updated_versions: List[Dict[str, Any]] = []
        for version_name in version_names:
            version = utility_versions.get(version_name, {"version": version_name, "groups": []})
            groups = [g for g in version.get("groups", []) if not is_generated_reference_group(g)]
            help_idx = next((i for i, g in enumerate(groups) if g.get("group") == "Help"), len(groups))
            groups.insert(help_idx, reference_group)
            version["groups"] = groups
            updated_versions.append(version)
        utilities["versions"] = updated_versions

    docs_json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render CNU OpenAPI lifecycle JSON to Mintlify pages")
    parser.add_argument("--input", required=True, help="Input lifecycle JSON path")
    parser.add_argument(
        "--overview",
        default="docs-main/global-synchronizer/reference/splice-apis.mdx",
        help="Overview MDX path",
    )
    parser.add_argument(
        "--specs-dir",
        default="docs-main/global-synchronizer/reference/splice-api-specs",
        help="Directory for per-spec MDX pages",
    )
    parser.add_argument(
        "--docs-json",
        default="docs.json",
        help="Path to docs.json",
    )
    parser.add_argument(
        "--update-docs-json",
        action="store_true",
        help="Update docs.json navigation for Utilities dropdown",
    )
    parser.add_argument(
        "--max-changed",
        type=int,
        default=300,
        help="Maximum changed entities rows per spec page",
    )
    parser.add_argument(
        "--max-ops",
        type=int,
        default=300,
        help="Maximum latest operations rows per spec page",
    )
    parser.add_argument(
        "--max-components",
        type=int,
        default=400,
        help="Maximum latest components rows per spec page",
    )
    parser.add_argument(
        "--max-endpoints",
        type=int,
        default=200,
        help="Maximum endpoints to render in endpoint reference section",
    )
    parser.add_argument(
        "--include-spec",
        default="",
        help="Optional regex filter for canonical spec_id",
    )
    parser.add_argument(
        "--exclude-spec",
        default="",
        help="Optional regex exclusion for canonical spec_id",
    )
    parser.add_argument(
        "--clean-specs-dir",
        action="store_true",
        help="Delete existing generated *.mdx files in specs-dir before rendering",
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    overview_path = Path(args.overview)
    specs_dir = Path(args.specs_dir)
    docs_json_path = Path(args.docs_json)
    include_spec_re = re.compile(args.include_spec) if args.include_spec else None
    exclude_spec_re = re.compile(args.exclude_spec) if args.exclude_spec else None

    if args.clean_specs_dir and specs_dir.exists():
        for f in specs_dir.glob("*.mdx"):
            f.unlink()

    spec_pages = write_spec_pages(
        payload=payload,
        specs_dir=specs_dir,
        max_changed=args.max_changed,
        max_ops=args.max_ops,
        max_components=args.max_components,
        max_endpoints=args.max_endpoints,
        include_spec_re=include_spec_re,
        exclude_spec_re=exclude_spec_re,
    )
    write_overview_page(payload=payload, overview_path=overview_path, spec_pages=spec_pages)

    if args.update_docs_json:
        update_docs_json(
            docs_json_path=docs_json_path,
            overview_path=overview_path,
            spec_paths=[p for _, p in spec_pages],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
