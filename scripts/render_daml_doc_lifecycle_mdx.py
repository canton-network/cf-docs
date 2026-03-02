#!/usr/bin/env python3
"""
Render DAML doc lifecycle JSON into Mintlify MDX pages.

Input:
  - JSON produced by scripts/daml_doc_lifecycle_mvp.py

Output:
  - One overview page
  - One details page per artifact
  - One reference page per discovered type (latest configured version)
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import urllib.parse
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def slugify(value: str) -> str:
    out = value.lower()
    out = re.sub(r"[^a-z0-9]+", "-", out)
    out = re.sub(r"-{2,}", "-", out).strip("-")
    return out


def md_code(text: str) -> str:
    out = str(text).replace("`", "\\`")
    out = out.replace("|", "\\|").replace("\n", " ").strip()
    return out


def md_text(text: str) -> str:
    out = html.escape(str(text), quote=False)
    out = out.replace("{", "&#123;").replace("}", "&#125;")
    out = out.replace("|", "\\|").replace("\n", " ").strip()
    return out


def strip_html_tags(fragment: str) -> str:
    no_tags = re.sub(r"<[^>]+>", "", fragment, flags=re.S)
    text = html.unescape(no_tags)
    return re.sub(r"\s+", " ", text).strip()


def normalize_doc_file(doc_path: str) -> str:
    p = urllib.parse.unquote(str(doc_path))
    p = p.split("#", 1)[0]
    if p.startswith("./"):
        p = p[2:]
    if p.startswith("/"):
        p = p[1:]
    return p


def symbol_doc_file(symbol: Dict[str, Any], artifact: Dict[str, Any], version: str) -> str:
    raw = symbol.get("doc_path")
    if raw:
        return normalize_doc_file(str(raw))

    links = symbol.get("doc_links", {})
    link = links.get(version) or latest_doc_link(symbol)
    if not link:
        return ""

    parsed = urllib.parse.urlparse(str(link))
    path = parsed.path or ""
    marker = f"/{artifact['artifact']}/{version}/"
    if marker in path:
        return normalize_doc_file(path.split(marker, 1)[1])
    return ""


def route_for_path(path: Path) -> str:
    s = path.as_posix()
    if s.endswith(".mdx"):
        s = s[:-4]
    return f"/{s}"


def changed_symbols(artifact: Dict[str, Any]) -> List[Dict[str, Any]]:
    base_version = artifact["versions"][0]
    out: List[Dict[str, Any]] = []
    for s in artifact["symbols"]:
        if (
            s.get("introduced_version") != base_version
            or s.get("deprecated_version") is not None
            or s.get("removed_version") is not None
        ):
            out.append(s)
    return out


def summarize_changes(artifact: Dict[str, Any]) -> Dict[str, int]:
    base_version = artifact["versions"][0]
    syms = artifact["symbols"]
    return {
        "introduced": sum(1 for s in syms if s.get("introduced_version") != base_version),
        "deprecated": sum(1 for s in syms if s.get("deprecated_version") is not None),
        "removed": sum(1 for s in syms if s.get("removed_version") is not None),
    }


def format_lifecycle_value(value: Optional[str], state: str) -> str:
    if not value:
        return "-"
    rendered = f"`{md_code(value)}`"
    if state == "deprecated":
        return f"⚠️ {rendered}"
    if state == "removed":
        return f"❌ {rendered}"
    return rendered


def lifecycle_title_prefix(has_deprecated: bool, has_removed: bool) -> str:
    if has_removed:
        return "❌ "
    if has_deprecated:
        return "⚠️ "
    return ""


def latest_doc_link(symbol: Dict[str, Any]) -> str:
    versions = symbol.get("versions_present", [])
    links = symbol.get("doc_links", {})
    if not versions:
        return ""
    latest = versions[-1]
    return links.get(latest, "")


def java_member_label(symbol: str) -> str:
    if "#" in symbol:
        return symbol.split("#", 1)[1]
    return symbol


def scala_member_owner_and_label(symbol_key: str) -> Tuple[str, str]:
    # symbol_key format: artifact:scala:member:{member_fqn}|{tail}|{link}
    if "member:" not in symbol_key:
        return "", symbol_key
    payload = symbol_key.split("member:", 1)[1]
    parts = payload.split("|", 2)
    if len(parts) < 2:
        return "", payload
    member_fqn = parts[0]
    tail = parts[1]
    owner = member_fqn.rsplit(".", 1)[0] if "." in member_fqn else ""
    member_name = member_fqn.rsplit(".", 1)[-1]
    label = f"{member_name}{tail}" if tail else member_name
    return owner, label


def parse_java_type_page(raw_html: str) -> Tuple[str, str]:
    signature = ""
    summary = ""

    m = re.search(r'<div class="type-signature">(.*?)</div>', raw_html, flags=re.S)
    if m:
        signature = strip_html_tags(m.group(1))

    class_desc = re.search(r'<section class="class-description".*?</section>', raw_html, flags=re.S)
    if class_desc:
        b = re.search(r'<div class="block">(.*?)</div>', class_desc.group(0), flags=re.S)
        if b:
            summary = strip_html_tags(b.group(1))

    if not summary:
        meta = re.search(r'<meta name="description" content="([^"]+)"', raw_html)
        if meta:
            summary = strip_html_tags(meta.group(1))

    return signature, summary


def parse_scala_type_page(raw_html: str) -> Tuple[str, str]:
    signature = ""
    summary = ""

    sig = re.search(r'<h4 id="signature" class="signature">(.*?)</h4>', raw_html, flags=re.S)
    if sig:
        signature = strip_html_tags(sig.group(1))

    cmt = re.search(
        r'<div id="comment" class="fullcommenttop">.*?<div class="comment cmt"><p>(.*?)</p>',
        raw_html,
        flags=re.S,
    )
    if cmt:
        summary = strip_html_tags(cmt.group(1))

    if not summary:
        meta = re.search(r'<meta content="([^"]+)" name="description"', raw_html)
        if meta:
            summary = strip_html_tags(meta.group(1))

    return signature, summary


def parse_type_metadata(
    artifact: Dict[str, Any],
    cache_dir: Path,
    type_symbols: List[Dict[str, Any]],
) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    latest_version = artifact["versions"][-1]
    jar_path = (
        cache_dir
        / artifact["group"]
        / artifact["artifact"]
        / latest_version
        / f"{artifact['artifact']}-{latest_version}-javadoc.jar"
    )
    if not jar_path.exists():
        return out

    language = artifact["language"]

    with zipfile.ZipFile(jar_path) as zf:
        names = set(zf.namelist())
        for sym in type_symbols:
            doc_file = symbol_doc_file(sym, artifact, latest_version)
            if not doc_file or doc_file not in names:
                continue
            raw = zf.read(doc_file).decode("utf-8", errors="replace")
            if language == "java":
                signature, summary = parse_java_type_page(raw)
            else:
                signature, summary = parse_scala_type_page(raw)
            out[sym["symbol_key"]] = {
                "signature": signature,
                "summary": summary,
            }

    return out


def render_changes_table(rows: List[Dict[str, Any]], limit: int) -> List[str]:
    if not rows:
        return ["No lifecycle changes detected in the configured version range.", ""]

    lines = [
        "| Docs | Symbol | Kind | Introduced | Deprecated | Removed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    shown = rows[:limit]
    for row in shown:
        symbol = f"`{md_code(row['symbol'])}`"
        kind = row.get("kind", "-")
        introduced = format_lifecycle_value(row.get("introduced_version"), "introduced")
        deprecated = format_lifecycle_value(row.get("deprecated_version"), "deprecated")
        removed = format_lifecycle_value(row.get("removed_version"), "removed")
        doc = latest_doc_link(row)
        doc_col = f"[Open]({doc})" if doc else "-"
        lines.append(f"| {doc_col} | {symbol} | `{kind}` | {introduced} | {deprecated} | {removed} |")

    if len(rows) > limit:
        lines.extend(
            [
                "",
                f"_Showing first {limit} rows out of {len(rows)} changed symbols._",
            ]
        )
    return lines + [""]


def write_type_page(
    page_path: Path,
    artifact: Dict[str, Any],
    type_symbol: Dict[str, Any],
    type_meta: Dict[str, str],
    members: List[Dict[str, Any]],
    artifact_route: str,
    max_members: int,
    has_deprecated: bool,
    has_removed: bool,
) -> None:
    lines: List[str] = []
    title = f"{lifecycle_title_prefix(has_deprecated, has_removed)}{type_symbol['symbol']}"
    latest_version = artifact["versions"][-1]
    signature = type_meta.get("signature", "")
    summary = type_meta.get("summary", "")

    lines.extend(
        [
            "---",
            f"title: \"{md_text(title)}\"",
            "description: \"Generated API reference page from published JavaDoc/ScalaDoc\"",
            "---",
            "",
            f"Back to [{artifact['artifact']} lifecycle]({artifact_route}).",
            "",
            "## Type",
            "",
            f"- Artifact: `{artifact['group']}:{artifact['artifact']}`",
            f"- Language: `{artifact['language']}`",
            f"- Latest rendered version: `{latest_version}`",
            f"- Introduced: {format_lifecycle_value(type_symbol.get('introduced_version'), 'introduced')}",
            f"- Deprecated: {format_lifecycle_value(type_symbol.get('deprecated_version'), 'deprecated')}",
            f"- Removed: {format_lifecycle_value(type_symbol.get('removed_version'), 'removed')}",
            "",
        ]
    )

    upstream = latest_doc_link(type_symbol)
    if upstream:
        lines.append(f"- Upstream docs: [Open]({upstream})")
        lines.append("")

    if signature:
        lines.extend(
            [
                "## Signature",
                "",
                "```text",
                signature,
                "```",
                "",
            ]
        )

    if summary:
        lines.extend(
            [
                "## Summary",
                "",
                md_text(summary),
                "",
            ]
        )

    lines.extend(["## Members", ""])
    if not members:
        lines.append("No members found for this type in the latest symbol index.")
        lines.append("")
    else:
        lines.extend(
            [
                "| Docs | Member | Introduced | Deprecated | Removed |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        shown = members[:max_members]
        for m in shown:
            if artifact["language"] == "java":
                member_label = java_member_label(m["symbol"])
            else:
                _, member_label = scala_member_owner_and_label(m["symbol_key"])
            introduced = format_lifecycle_value(m.get("introduced_version"), "introduced")
            deprecated = format_lifecycle_value(m.get("deprecated_version"), "deprecated")
            removed = format_lifecycle_value(m.get("removed_version"), "removed")
            link = latest_doc_link(m)
            link_col = f"[Open]({link})" if link else "-"
            lines.append(
                f"| {link_col} | `{md_code(member_label)}` | {introduced} | {deprecated} | {removed} |"
            )

        if len(members) > max_members:
            lines.extend(
                [
                    "",
                    f"_Showing first {max_members} members out of {len(members)}._",
                ]
            )
        lines.append("")

    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text("\n".join(lines), encoding="utf-8")


def write_artifact_page(
    path: Path,
    artifact: Dict[str, Any],
    overview_route: str,
    type_rows: List[Dict[str, Any]],
    max_rows: int,
    max_types: int,
) -> str:
    changes = changed_symbols(artifact)
    summary = summarize_changes(artifact)
    versions = artifact["versions"]
    if artifact["artifact"] == "bindings-java":
        title = "Bindings Lifecycle Overview"
    else:
        title = (
            f"{lifecycle_title_prefix(summary['deprecated'] > 0, summary['removed'] > 0)}"
            f"{artifact['artifact']} Lifecycle"
        )

    lines: List[str] = []
    lines.extend(
        [
            "---",
            f"title: \"{md_text(title)}\"",
            "description: \"Generated lifecycle timeline and reference index from published JavaDoc/ScalaDoc artifacts\"",
            "---",
            "",
            f"Back to [Lifecycle overview]({overview_route}).",
            "",
            "## Artifact",
            "",
            f"- Group: `{artifact['group']}`",
            f"- Artifact: `{artifact['artifact']}`",
            f"- Language: `{artifact['language']}`",
            f"- Versions: `{', '.join(versions)}`",
            f"- Total symbols tracked: `{artifact['symbol_count']}`",
            "",
            "## Lifecycle Summary",
            "",
            f"- Introduced in range: `{summary['introduced']}`",
            f"- Deprecated in range: `{summary['deprecated']}`",
            f"- Removed in range: `{summary['removed']}`",
            "",
            "## Type Reference (Latest Version)",
            "",
            "| Local Page | Upstream | Type | Summary | Introduced | Deprecated | Removed |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    shown_types = type_rows[:max_types]
    for row in shown_types:
        t = row["type"]
        summary_text = md_text(row.get("summary") or "")
        introduced = format_lifecycle_value(t.get("introduced_version"), "introduced")
        deprecated = format_lifecycle_value(t.get("deprecated_version"), "deprecated")
        removed = format_lifecycle_value(t.get("removed_version"), "removed")
        local = f"[Open]({row['local_route']})"
        upstream_link = latest_doc_link(t)
        upstream = f"[Open]({upstream_link})" if upstream_link else "-"
        lines.append(
            f"| {local} | {upstream} | `{md_code(t['symbol'])}` | {summary_text} | {introduced} | {deprecated} | {removed} |"
        )

    if len(type_rows) > max_types:
        lines.extend(
            [
                "",
                f"_Showing first {max_types} types out of {len(type_rows)}._",
            ]
        )

    lines.extend(["", "## Changed Symbols", ""])
    lines.extend(render_changes_table(changes, max_rows))

    deprecated_rows = [r for r in changes if r.get("deprecated_version") is not None]
    if deprecated_rows:
        lines.extend(
            [
                "## Deprecation Notes",
                "",
                "| Symbol | Deprecated | Note |",
                "| --- | --- | --- |",
            ]
        )
        for row in deprecated_rows[:max_rows]:
            lines.append(
                f"| `{md_code(row['symbol'])}` | {row.get('deprecated_version') or '-'} | {md_text(row.get('deprecation_note') or '-')} |"
            )
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path.name


def write_overview_page(
    out_path: Path,
    details_dir_route: str,
    payload: Dict[str, Any],
    detail_files: Dict[str, str],
) -> None:
    artifacts = payload["artifacts"]

    lines: List[str] = []
    lines.extend(
        [
            "---",
            "title: \"Ledger Bindings API Lifecycle (MVP)\"",
            "description: \"Generated lifecycle timeline and reference pages for DAML Java/Scala bindings\"",
            "---",
            "",
            "This page is generated from published `-javadoc.jar` artifacts on Maven Central.",
            "",
            f"- Generated at (UTC): `{payload.get('generated_at_utc', 'unknown')}`",
            f"- Source JSON: `{payload.get('config_path', 'unknown')}`",
            "",
            "## Artifacts",
            "",
            "| Details | Artifact | Language | Versions | Symbols | Introduced | Deprecated | Removed |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for a in artifacts:
        summary = summarize_changes(a)
        versions = ", ".join(a["versions"])
        detail = detail_files.get(a["artifact"], "")
        detail_link = f"[View]({details_dir_route}/{detail.replace('.mdx', '')})" if detail else "-"
        lines.append(
            f"| {detail_link} | `{a['group']}:{a['artifact']}` | `{a['language']}` | `{md_text(versions)}` | `{a['symbol_count']}` | `{summary['introduced']}` | `{summary['deprecated']}` | `{summary['removed']}` |"
        )

    lines.extend(
        [
            "",
            "## Regenerate",
            "",
            "```bash",
            "cd /Users/danielporter/new-docs",
            "python3 scripts/daml_doc_lifecycle_mvp.py \\",
            "  --config config/daml-doc-lifecycle-mvp.sample.json \\",
            "  --output .internal/generated/daml-doc-lifecycle-mvp.json",
            "python3 scripts/render_daml_doc_lifecycle_mdx.py \\",
            "  --input .internal/generated/daml-doc-lifecycle-mvp.json \\",
            "  --overview docs-main/appdev/modules/m4-ledger-bindings-api-lifecycle.mdx \\",
            "  --details-dir docs-main/appdev/reference/ledger-bindings-api-lifecycle",
            "```",
            "",
            "## Notes",
            "",
            "- Java and Scala type pages are generated from latest configured version docs.",
            "- Java deprecation metadata is best-effort from `deprecated-list.html`.",
            "- Scala deprecation is not inferred in this MVP.",
            "- `removed` means first configured version after last observed presence.",
            "",
        ]
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def build_type_reference_rows(
    artifact: Dict[str, Any],
    metadata: Dict[str, Dict[str, str]],
    details_dir: Path,
    artifact_slug: str,
    artifact_route: str,
    max_members: int,
) -> List[Dict[str, Any]]:
    symbols = artifact["symbols"]
    language = artifact["language"]
    latest_version = artifact["versions"][-1]

    type_symbols = [s for s in symbols if s.get("kind") == "type"]
    type_symbols.sort(key=lambda s: s["symbol"])

    doc_to_type_key: Dict[str, str] = {}
    type_by_key: Dict[str, Dict[str, Any]] = {}
    for t in type_symbols:
        key = t["symbol_key"]
        type_by_key[key] = t
        doc_file = symbol_doc_file(t, artifact, latest_version)
        if doc_file:
            doc_to_type_key[doc_file] = key

    type_status: Dict[str, Dict[str, bool]] = {
        key: {
            "deprecated": t.get("deprecated_version") is not None,
            "removed": t.get("removed_version") is not None,
        }
        for key, t in type_by_key.items()
    }
    type_name_to_key = {t["symbol"]: key for key, t in type_by_key.items()}

    members_by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    member_symbols = [s for s in symbols if s.get("kind") == "member"]
    for m in member_symbols:
        # Capture lifecycle markers for titles based on ownership, regardless of
        # whether the member is still present in latest docs.
        if m.get("deprecated_version") is not None or m.get("removed_version") is not None:
            if language == "java":
                owner = m.get("symbol", "").split("#", 1)[0] if "#" in m.get("symbol", "") else ""
                key = type_name_to_key.get(owner)
                if key:
                    if m.get("deprecated_version") is not None:
                        type_status[key]["deprecated"] = True
                    if m.get("removed_version") is not None:
                        type_status[key]["removed"] = True
            else:
                owner, _ = scala_member_owner_and_label(m.get("symbol_key", ""))
                best_key = ""
                best_len = -1
                for type_name, key in type_name_to_key.items():
                    if owner == type_name or owner.startswith(type_name + "."):
                        if len(type_name) > best_len:
                            best_len = len(type_name)
                            best_key = key
                if best_key:
                    if m.get("deprecated_version") is not None:
                        type_status[best_key]["deprecated"] = True
                    if m.get("removed_version") is not None:
                        type_status[best_key]["removed"] = True

        doc_file = symbol_doc_file(m, artifact, latest_version)
        type_key = doc_to_type_key.get(doc_file)
        if not type_key:
            continue

        # Keep member ownership tight for Scala to avoid inherited Any/AnyRef members.
        if language == "scala":
            owner, _ = scala_member_owner_and_label(m.get("symbol_key", ""))
            type_symbol = type_by_key[type_key]["symbol"]
            if owner and not owner.startswith(type_symbol):
                continue

        if language == "java":
            owner = m.get("symbol", "").split("#", 1)[0] if "#" in m.get("symbol", "") else ""
            type_symbol = type_by_key[type_key]["symbol"]
            if owner and owner != type_symbol:
                continue

        members_by_type[type_key].append(m)

    rows: List[Dict[str, Any]] = []
    type_pages_dir = details_dir / f"{artifact_slug}-types"

    for t in type_symbols:
        key = t["symbol_key"]
        type_symbol = t["symbol"]
        token = hashlib.sha1(type_symbol.encode("utf-8")).hexdigest()[:10]
        file_name = f"{slugify(type_symbol.rsplit('.', 1)[-1])}-{token}.mdx"
        page_path = type_pages_dir / file_name
        page_route = route_for_path(page_path)

        type_meta = metadata.get(key, {})
        members = sorted(
            members_by_type.get(key, []),
            key=lambda m: m.get("symbol", ""),
        )

        write_type_page(
            page_path=page_path,
            artifact=artifact,
            type_symbol=t,
            type_meta=type_meta,
            members=members,
            artifact_route=artifact_route,
            max_members=max_members,
            has_deprecated=type_status[key]["deprecated"],
            has_removed=type_status[key]["removed"],
        )

        rows.append(
            {
                "type": t,
                "summary": type_meta.get("summary", ""),
                "local_route": page_route,
            }
        )

    rows.sort(key=lambda r: r["type"]["symbol"])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Render DAML lifecycle JSON to Mintlify pages")
    parser.add_argument("--input", required=True, help="Input lifecycle JSON path")
    parser.add_argument(
        "--overview",
        required=True,
        help="Overview MDX output path (for nav entry)",
    )
    parser.add_argument(
        "--details-dir",
        required=True,
        help="Directory for per-artifact MDX pages",
    )
    parser.add_argument(
        "--cache-dir",
        default=".internal/cache/daml-doc-lifecycle-mvp",
        help="Cache directory used by the extractor; read latest type docs from here.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=300,
        help="Max number of changed rows to render per artifact page",
    )
    parser.add_argument(
        "--max-types",
        type=int,
        default=1000,
        help="Max number of types to render in artifact type table",
    )
    parser.add_argument(
        "--max-members",
        type=int,
        default=400,
        help="Max number of members to render per type page",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    overview_path = Path(args.overview)
    details_dir = Path(args.details_dir)
    cache_dir = Path(args.cache_dir)

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    artifacts = payload.get("artifacts", [])
    if not artifacts:
        raise ValueError("Input JSON has no artifacts.")

    overview_route = route_for_path(overview_path)
    details_route = "/" + str(details_dir)

    detail_files: Dict[str, str] = {}

    for artifact in artifacts:
        artifact_slug = slugify(artifact["artifact"])
        artifact_page_path = details_dir / f"{artifact_slug}.mdx"
        artifact_route = route_for_path(artifact_page_path)

        type_symbols = [s for s in artifact["symbols"] if s.get("kind") == "type"]
        metadata = parse_type_metadata(artifact=artifact, cache_dir=cache_dir, type_symbols=type_symbols)

        type_rows = build_type_reference_rows(
            artifact=artifact,
            metadata=metadata,
            details_dir=details_dir,
            artifact_slug=artifact_slug,
            artifact_route=artifact_route,
            max_members=args.max_members,
        )

        fn = write_artifact_page(
            path=artifact_page_path,
            artifact=artifact,
            overview_route=overview_route,
            type_rows=type_rows,
            max_rows=args.max_rows,
            max_types=args.max_types,
        )
        detail_files[artifact["artifact"]] = fn

    write_overview_page(
        out_path=overview_path,
        details_dir_route=details_route,
        payload=payload,
        detail_files=detail_files,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
