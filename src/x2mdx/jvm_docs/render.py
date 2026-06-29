"""Render JVM doc lifecycle reports into MDX pages."""

from __future__ import annotations

import hashlib
import html
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

from x2mdx.jvm_docs.models import JvmDocArtifactLifecycle, JvmDocLifecycleReport, JvmDocSymbolLifecycle
from x2mdx.output import Page
from x2mdx.templating import markdown_page

CHANGE_MARKER = "🔵"
TIMELINE_MARKERS = {
    "active": "🟢",
    "removed": "🔴",
}


def slugify(value: str) -> str:
    out = value.lower()
    out = re.sub(r"[^a-z0-9]+", "-", out)
    return re.sub(r"-{2,}", "-", out).strip("-")


def md_code(text: str) -> str:
    out = str(text).replace("`", "\\`")
    return out.replace("|", "\\|").replace("\n", " ").strip()


def md_text(text: str) -> str:
    out = html.escape(str(text), quote=False)
    out = out.replace("\\", "\\\\")
    out = out.replace("{", "\\{").replace("}", "\\}").replace("$", "\\$")
    return out.replace("|", "\\|").replace("\n", " ").strip()


def markdown_link_target(target: str) -> str:
    return quote(str(target), safe="/#:?&=%;,+-._~")


def markdown_link(label: str, target: str) -> str:
    return f"[{label}](<{markdown_link_target(target)}>)"


def page_path(root: Path, target: Path) -> str:
    return Path(os.path.relpath(target, start=root)).as_posix()


def relative_page_link(from_path: Path, to_path: Path) -> str:
    relative = os.path.relpath(to_path.with_suffix(""), start=from_path.parent)
    link = Path(relative).as_posix()
    if not link.startswith("."):
        return f"./{link}"
    return link


def compute_output_root(overview_output: Path, details_dir: Path) -> Path:
    common = os.path.commonpath([os.path.abspath(str(overview_output)), os.path.abspath(str(details_dir))])
    return Path(common)


def latest_doc_link(symbol: JvmDocSymbolLifecycle) -> str:
    if not symbol.versions_present:
        return ""
    latest_version = symbol.versions_present[-1]
    return symbol.doc_links.get(latest_version, "")


def latest_doc_markdown_link(symbol: JvmDocSymbolLifecycle, *, label: str = "Open") -> str:
    target = latest_doc_link(symbol)
    if not target:
        return "-"
    return markdown_link(label, target)


def changed_symbols(artifact: JvmDocArtifactLifecycle) -> list[JvmDocSymbolLifecycle]:
    base_version = artifact.versions[0]
    return [
        symbol
        for symbol in artifact.symbols
        if symbol.introduced_version != base_version
        or symbol.deprecated_version is not None
        or symbol.removed_version is not None
    ]


def summarize_changes(artifact: JvmDocArtifactLifecycle) -> dict[str, int]:
    base_version = artifact.versions[0]
    return {
        "introduced": sum(1 for symbol in artifact.symbols if symbol.introduced_version != base_version),
        "deprecated": sum(1 for symbol in artifact.symbols if symbol.deprecated_version is not None),
        "removed": sum(1 for symbol in artifact.symbols if symbol.removed_version is not None),
    }


def format_lifecycle_value(value: str | None) -> str:
    if not value:
        return "-"
    return f"`{md_code(value)}`"


def type_label(type_text: str, package_name: str) -> str:
    prefix = f"{package_name}."
    if package_name != "(root package)" and type_text.startswith(prefix):
        return type_text[len(prefix) :]
    return type_text


def summary_preview(text: str, *, max_length: int = 72) -> str:
    normalized = " ".join(str(text).split())
    if not normalized:
        return ""
    if len(normalized) <= max_length:
        return md_text(normalized)
    clipped = normalized[: max_length - 3].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    if len(clipped) < max_length // 2:
        clipped = normalized[: max_length - 3].rstrip(" ,.;:-")
    return md_text(f"{clipped}...")


def status_cell(status: str | None) -> str:
    return f"`{md_code(status)}`" if status else "-"


def package_toc_legend() -> str:
    return "  ".join(
        [
            f'{TIMELINE_MARKERS["active"]} Active Since',
            f"{CHANGE_MARKER} Changed",
            f'{TIMELINE_MARKERS["removed"]} Removed',
        ]
    )


def timeline_marker(marker: str, version: str) -> str:
    return f"{marker} `{md_code(version)}`"


def status_timeline_cell(
    *,
    introduced_version: str,
    changed_versions: list[str] | None = None,
    removed_version: str | None = None,
) -> str:
    parts = [timeline_marker(TIMELINE_MARKERS["active"], introduced_version)]
    for version in changed_versions or []:
        parts.append(timeline_marker(CHANGE_MARKER, version))
    if removed_version:
        parts.append(timeline_marker(TIMELINE_MARKERS["removed"], removed_version))
    return " ".join(parts)


def package_removed_version(symbols: list[JvmDocSymbolLifecycle], version_index: dict[str, int]) -> str | None:
    type_symbols = [symbol for symbol in symbols if symbol.kind == "type"]
    if not type_symbols or any(symbol.removed_version is None for symbol in type_symbols):
        return None
    return max(
        (symbol.removed_version for symbol in type_symbols if symbol.removed_version),
        key=lambda version: version_index[version],
    )


def package_introduced_version(symbols: list[JvmDocSymbolLifecycle], version_index: dict[str, int]) -> str:
    return min((symbol.introduced_version for symbol in symbols), key=lambda version: version_index[version])


def package_changed_versions(
    symbols: list[JvmDocSymbolLifecycle],
    version_index: dict[str, int],
    *,
    introduced_version: str,
    removed_version: str | None,
) -> list[str]:
    versions = {
        version
        for symbol in symbols
        for version in [symbol.introduced_version, symbol.deprecated_version, symbol.removed_version]
        if version
    }
    versions.discard(introduced_version)
    if removed_version is not None:
        versions.discard(removed_version)
    return sorted(versions, key=lambda version: version_index[version])


def package_summary_text(
    *,
    type_count: int,
    introduced_count: int,
    deprecated_count: int,
    removed_count: int,
    removed_version: str | None,
) -> str:
    type_label_text = "type" if type_count == 1 else "types"
    changes: list[str] = []
    if introduced_count:
        changes.append(f"{introduced_count} introduced")
    if deprecated_count:
        changes.append(f"{deprecated_count} deprecated")
    if removed_count:
        changes.append(f"{removed_count} removed")

    if changes:
        summary = f"{type_count} {type_label_text}. Changes in range: {', '.join(changes)}."
    else:
        summary = f"{type_count} {type_label_text}. No lifecycle changes in selected range."

    if removed_version is not None:
        summary = f"{summary} Package removed in {removed_version}."
    return md_text(summary)


def combined_summary(summary: str | None, removed_version: str | None) -> str:
    parts: list[str] = []
    if summary:
        parts.append(summary)
    if removed_version:
        parts.append(f"Removed in {removed_version}.")
    return " ".join(parts).strip()


def object_page_description(symbol: JvmDocSymbolLifecycle, object_name: str) -> str:
    if symbol.latest_summary:
        return symbol.latest_summary
    return f"Generated object reference page for {object_name} from local Javadoc/Scaladoc snapshots."


def java_member_owner(symbol: JvmDocSymbolLifecycle) -> str:
    if "#" not in symbol.symbol:
        return ""
    return symbol.symbol.split("#", 1)[0]


def java_member_label(symbol: JvmDocSymbolLifecycle) -> str:
    if "#" not in symbol.symbol:
        return symbol.symbol
    return symbol.symbol.split("#", 1)[1]


def scala_member_owner_and_label(symbol: JvmDocSymbolLifecycle) -> tuple[str, str]:
    if "member:" not in symbol.symbol_key:
        return "", symbol.symbol
    payload = symbol.symbol_key.split("member:", 1)[1]
    parts = payload.split("|", 2)
    member_fqn = parts[0]
    tail = parts[1] if len(parts) > 1 else ""
    owner = member_fqn.rsplit(".", 1)[0] if "." in member_fqn else ""
    member_name = member_fqn.rsplit(".", 1)[-1]
    label = f"{member_name}{tail}" if tail else member_name
    return owner, label


def package_name_for_symbol(symbol: JvmDocSymbolLifecycle) -> str:
    doc_path = symbol.latest_doc_path.strip("/")
    package_path = Path(doc_path).parent.as_posix().strip(".")
    if package_path and package_path != ".":
        return package_path.replace("/", ".")
    if symbol.kind == "type" and "." in symbol.symbol:
        return symbol.symbol.rsplit(".", 1)[0]
    if symbol.kind == "member":
        if symbol.language == "java":
            owner = java_member_owner(symbol)
        else:
            owner, _ = scala_member_owner_and_label(symbol)
        if "." in owner:
            return owner.rsplit(".", 1)[0]
    return "(root package)"


def build_object_slug(label: str, *, used_slugs: set[str]) -> str:
    base = slugify(label) or "object"
    if base not in used_slugs:
        used_slugs.add(base)
        return base

    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
    candidate = f"{base}-{digest}"
    used_slugs.add(candidate)
    return candidate


def build_type_entries(
    artifact: JvmDocArtifactLifecycle,
) -> list[dict[str, Any]]:
    type_symbols = sorted((symbol for symbol in artifact.symbols if symbol.kind == "type"), key=lambda symbol: symbol.symbol)
    member_symbols = [symbol for symbol in artifact.symbols if symbol.kind == "member"]
    type_by_symbol = {symbol.symbol: symbol for symbol in type_symbols}
    members_by_type: dict[str, list[JvmDocSymbolLifecycle]] = defaultdict(list)

    for member in member_symbols:
        if artifact.language == "java":
            owner = java_member_owner(member)
            type_symbol = type_by_symbol.get(owner)
            if type_symbol is None:
                continue
            members_by_type[type_symbol.symbol_key].append(member)
            continue

        owner, _ = scala_member_owner_and_label(member)
        best_match: JvmDocSymbolLifecycle | None = None
        best_length = -1
        for type_symbol in type_symbols:
            if owner == type_symbol.symbol or owner.startswith(type_symbol.symbol + "."):
                if len(type_symbol.symbol) > best_length:
                    best_match = type_symbol
                    best_length = len(type_symbol.symbol)
        if best_match is None:
            continue
        members_by_type[best_match.symbol_key].append(member)

    entries: list[dict[str, Any]] = []
    for type_symbol in type_symbols:
        package_name = package_name_for_symbol(type_symbol)
        object_name = type_label(type_symbol.symbol, package_name)
        summary_text = combined_summary(type_symbol.latest_summary, type_symbol.removed_version)
        type_members = sorted(members_by_type.get(type_symbol.symbol_key, []), key=lambda symbol: symbol.symbol)
        member_rows: list[list[str]] = []

        for member in type_members:
            if artifact.language == "java":
                member_label = java_member_label(member)
            else:
                _, member_label = scala_member_owner_and_label(member)
            upstream_link = latest_doc_link(member)
            member_rows.append(
                [
                    markdown_link("Open", upstream_link) if upstream_link else "-",
                    f"`{md_code(member_label)}`",
                    format_lifecycle_value(member.introduced_version),
                    format_lifecycle_value(member.deprecated_version),
                    format_lifecycle_value(member.removed_version),
                ]
            )

        entries.append(
            {
                "object_name": object_name,
                "package": package_name,
                "status": type_symbol.status,
                "status_cell": status_cell(type_symbol.status),
                "summary_preview": summary_preview(summary_text) or "-",
                "description": object_page_description(type_symbol, object_name),
                "removed_notice": f"Removed in `{md_code(type_symbol.removed_version)}`." if type_symbol.removed_version else "",
                "upstream": latest_doc_markdown_link(type_symbol),
                "signature": type_symbol.latest_signature or "",
                "member_rows": member_rows,
                "symbol": type_symbol,
            }
        )

    return entries


def build_package_rows_and_pages(
    artifact: JvmDocArtifactLifecycle,
    *,
    root: Path,
    details_dir: Path,
    artifact_page_path: Path,
) -> tuple[list[dict[str, str]], list[Page]]:
    type_entries = build_type_entries(artifact)
    package_pages_dir = details_dir / f"{slugify(artifact.artifact)}-packages"
    package_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    package_symbol_groups: dict[str, list[JvmDocSymbolLifecycle]] = defaultdict(list)
    for entry in type_entries:
        package_groups[str(entry["package"])].append(entry)
    for symbol in artifact.symbols:
        package_symbol_groups[package_name_for_symbol(symbol)].append(symbol)

    version_index = {version: index for index, version in enumerate(artifact.versions)}
    artifact_rows: list[dict[str, str]] = []
    pages: list[Page] = []

    for package_name in sorted(package_groups):
        package_dir = package_pages_dir / slugify(package_name)
        package_page_path = package_dir / "index.mdx"
        used_slugs: set[str] = set()

        package_entries = sorted(package_groups[package_name], key=lambda item: str(item["object_name"]))
        for entry in package_entries:
            entry["page_path"] = package_dir / f"{build_object_slug(str(entry['object_name']), used_slugs=used_slugs)}.mdx"

        package_symbols = package_symbol_groups[package_name]
        type_symbols = [symbol for symbol in package_symbols if symbol.kind == "type"]
        introduced_count = sum(1 for symbol in type_symbols if symbol.introduced_version != artifact.versions[0])
        deprecated_count = sum(1 for symbol in type_symbols if symbol.deprecated_version is not None)
        removed_count = sum(1 for symbol in type_symbols if symbol.removed_version is not None)
        introduced_version = package_introduced_version(package_symbols, version_index)
        removed_version = package_removed_version(package_symbols, version_index)
        changed_versions = package_changed_versions(
            package_symbols,
            version_index,
            introduced_version=introduced_version,
            removed_version=removed_version,
        )

        pages.append(
            markdown_page(
                path=page_path(root, package_page_path),
                title="Overview",
                description=f"Object index for package {package_name}.",
                template_name="jvm_docs/package.md.j2",
                package_heading=f"Package `{md_code(package_name)}`",
                object_rows=[
                    [
                        f"[`{md_code(str(entry['object_name']))}`]({relative_page_link(package_page_path, Path(entry['page_path']))})",
                        str(entry["status_cell"]),
                        str(entry["summary_preview"]),
                    ]
                    for entry in package_entries
                ],
            )
        )

        for entry in package_entries:
            symbol = entry["symbol"]
            page_path_obj = Path(entry["page_path"])
            pages.append(
                markdown_page(
                    path=page_path(root, page_path_obj),
                    title=str(entry["object_name"]),
                    description=str(entry["description"]),
                    template_name="jvm_docs/object.md.j2",
                    object_heading=(
                        f"{entry['object_name']} - {entry['status']}"
                        if entry["status"]
                        else str(entry["object_name"])
                    ),
                    docs_link=str(entry["upstream"]),
                    removed_notice=str(entry["removed_notice"]),
                    signature=symbol.latest_signature or "",
                    member_rows=entry["member_rows"],
                )
            )

        artifact_rows.append(
            {
                "name": f"[`{md_code(package_name)}`]({relative_page_link(artifact_page_path, package_page_path)})",
                "status": status_timeline_cell(
                    introduced_version=introduced_version,
                    changed_versions=changed_versions,
                    removed_version=removed_version,
                ),
                "summary": package_summary_text(
                    type_count=len(package_entries),
                    introduced_count=introduced_count,
                    deprecated_count=deprecated_count,
                    removed_count=removed_count,
                    removed_version=removed_version,
                ),
            }
        )

    return artifact_rows, pages


def build_artifact_page(
    artifact: JvmDocArtifactLifecycle,
    *,
    root: Path,
    overview_output: Path,
    details_dir: Path,
) -> tuple[Page, list[Page]]:
    artifact_slug = slugify(artifact.artifact)
    artifact_page_path = details_dir / f"{artifact_slug}.mdx"
    package_rows, package_pages = build_package_rows_and_pages(
        artifact,
        root=root,
        details_dir=details_dir,
        artifact_page_path=artifact_page_path,
    )
    change_summary = summarize_changes(artifact)

    changed_rows = [
        [
            latest_doc_markdown_link(symbol),
            f"`{md_code(symbol.symbol)}`",
            f"`{md_code(symbol.kind)}`",
            format_lifecycle_value(symbol.introduced_version),
            format_lifecycle_value(symbol.deprecated_version),
            format_lifecycle_value(symbol.removed_version),
        ]
        for symbol in changed_symbols(artifact)
    ]

    deprecations = [symbol for symbol in changed_symbols(artifact) if symbol.deprecated_version]

    artifact_page = markdown_page(
        path=page_path(root, artifact_page_path),
        title=f"{artifact.artifact} lifecycle",
        description="Generated lifecycle timeline and package index from local Javadoc/Scaladoc snapshots",
        template_name="jvm_docs/artifact.md.j2",
        overview_link=relative_page_link(artifact_page_path, overview_output),
        version_summary_items=[
            f"Group: `{md_code(artifact.group)}`",
            f"Artifact: `{md_code(artifact.artifact)}`",
            f"Language: `{md_code(artifact.language)}`",
            f"Versions: `{md_code(', '.join(artifact.versions))}`",
            f"Total symbols tracked: `{artifact.symbol_count}`",
            f"Types: `{artifact.type_count}`",
            f"Members: `{artifact.member_count}`",
            f"Introduced in range: `{change_summary['introduced']}`",
            f"Deprecated in range: `{change_summary['deprecated']}`",
            f"Removed in range: `{change_summary['removed']}`",
        ],
        package_toc_legend=package_toc_legend(),
        package_toc_rows=[[row["name"], row["status"], row["summary"]] for row in package_rows],
        changed_rows=changed_rows,
        deprecation_rows=[
            [
                f"`{md_code(symbol.symbol)}`",
                format_lifecycle_value(symbol.deprecated_version),
                md_text(symbol.deprecation_note or "-"),
            ]
            for symbol in deprecations
        ],
        failure_rows=[
            [
                f"`{md_code(failure.get('version', '-'))}`",
                f"`{md_code(failure.get('jar_path', '-'))}`",
                md_text(failure.get("error", "-")),
            ]
            for failure in artifact.failures
        ],
    )
    return artifact_page, package_pages


def build_pages(
    report: JvmDocLifecycleReport,
    *,
    overview_output: Path,
    details_dir: Path,
    overview_title: str = "JVM API Lifecycle",
) -> tuple[Path, list[Page]]:
    root = compute_output_root(overview_output, details_dir)
    pages: list[Page] = []

    artifact_pages: list[tuple[JvmDocArtifactLifecycle, Page]] = []
    extra_pages: list[Page] = []
    for artifact in report.artifacts:
        artifact_page, type_pages = build_artifact_page(
            artifact,
            root=root,
            overview_output=overview_output,
            details_dir=details_dir,
        )
        artifact_pages.append((artifact, artifact_page))
        extra_pages.extend(type_pages)

    overview_rows = []
    for artifact, artifact_page in artifact_pages:
        summary = summarize_changes(artifact)
        overview_rows.append(
            [
                f"[View]({relative_page_link(overview_output, root / artifact_page.path)})",
                f"`{md_code(f'{artifact.group}:{artifact.artifact}')}`",
                f"`{md_code(artifact.language)}`",
                f"`{md_code(', '.join(artifact.versions))}`",
                f"`{artifact.symbol_count}`",
                f"`{summary['introduced']}`",
                f"`{summary['deprecated']}`",
                f"`{summary['removed']}`",
            ]
        )

    overview_page = markdown_page(
        path=page_path(root, overview_output),
        title=overview_title,
        description="Generated lifecycle timeline and reference pages for local Javadoc/Scaladoc artifacts",
        template_name="jvm_docs/overview.md.j2",
        source_items=[
            f"Source name: `{md_code(report.source_name)}`",
            f"Version filter: `{md_code(report.version_filter)}`",
            f"Artifacts: `{report.summary['artifact_count']}`",
            f"Types: `{report.summary['type_count']}`",
            f"Members: `{report.summary['member_count']}`",
        ],
        overview_rows=overview_rows,
        notes=[md_text(note) for note in report.notes],
    )

    pages.append(overview_page)
    pages.extend(page for _, page in artifact_pages)
    pages.extend(extra_pages)
    return root, pages
