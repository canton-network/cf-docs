#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from ledger_api_release_bundles import (
    ensure_bundle_archive,
    load_json,
    materialize_bundle_spec,
    read_bundle_spec_text,
    selected_versions,
)
import reference_nav
from x2mdx.output import Page, RawMarkdown
from x2mdx.reference_pages import (
    ReferenceBadge,
    ReferenceCard,
    ReferenceCollectionPage,
    ReferenceMetaItem,
    ReferenceSection,
    compact_text,
    render_collection_page,
    safe_markdown_text,
)
from x2mdx.render import write_page


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "x2mdx"
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "ledger-api" / "source-artifacts.json"
DEFAULT_CACHE_DIR = DEFAULT_CACHE_ROOT / "ledger-api-bundles"
DEFAULT_OUTPUT_SPEC = REPO_ROOT / "docs-main" / "openapi" / "json-ledger-api" / "openapi.yaml"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
DEFAULT_NAV_DROPDOWN = "API Reference"
DEFAULT_PARENT_GROUP = "Ledger API"
DEFAULT_GROUP_LABEL = "OpenAPI"
DEFAULT_OPENAPI_DIRECTORY = "reference/json-api-reference"
DEFAULT_DETAILS_PAGE_REF = "reference/json-api-reference/details"
LEGACY_OUTPUT_FILE = REPO_ROOT / "docs-main" / "reference" / "json-api-reference.mdx"
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish the latest JSON Ledger API OpenAPI spec for Mintlify's native API rendering "
            "and wire the OpenAPI section in docs.json."
        )
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--output-spec", default=str(DEFAULT_OUTPUT_SPEC))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--nav-dropdown", default=DEFAULT_NAV_DROPDOWN)
    parser.add_argument("--parent-group", default=DEFAULT_PARENT_GROUP)
    parser.add_argument("--group-label", default=DEFAULT_GROUP_LABEL)
    parser.add_argument("--openapi-directory", default=DEFAULT_OPENAPI_DIRECTORY)
    parser.add_argument("--details-page-ref", default=DEFAULT_DETAILS_PAGE_REF)
    parser.add_argument("--publish-version", help="Explicit docs major version to publish.")
    parser.add_argument(
        "--version",
        action="append",
        help="Restrict candidate versions before selecting the publish version. Repeat to filter the set.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Refresh cached Canton release bundles and rewrite the published OpenAPI spec even if cached.",
    )
    return parser.parse_args()


def docs_relative_file_ref(path: Path, docs_json_path: Path) -> str:
    return path.resolve().relative_to(docs_json_path.resolve().parent).as_posix()


def _find_group(items: list[Any], label: str) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and item.get("group") == label:
            return item
    return None


def resolve_publish_version(
    *,
    source_config: dict[str, Any],
    versions: list[dict[str, str]],
    requested_version: str | None,
) -> dict[str, str]:
    publish_version = requested_version
    if publish_version is None:
        configured = source_config.get("publish_version")
        if isinstance(configured, str) and configured.strip():
            publish_version = configured.strip()

    if publish_version is None:
        return versions[-1]

    selected = next((entry for entry in versions if entry["version"] == publish_version), None)
    if selected is None:
        available = ", ".join(entry["version"] for entry in versions)
        raise ValueError(f"Publish version '{publish_version}' not found in selected versions: {available}")
    return selected


def update_docs_navigation(
    *,
    docs_json_path: Path,
    dropdown_label: str,
    parent_group_label: str,
    group_label: str,
    openapi_source_ref: str,
    openapi_directory: str,
    details_page_ref: str,
    openapi_page_refs: list[str],
) -> None:
    payload = load_json(docs_json_path)
    pages = reference_nav.navigation_pages(payload, label=dropdown_label, docs_json_path=docs_json_path)

    parent_group = _find_group(pages, parent_group_label)
    if parent_group is None:
        raise ValueError(f"Parent group not found in docs.json: {parent_group_label}")

    parent_pages = parent_group.get("pages")
    if not isinstance(parent_pages, list):
        raise ValueError(f"Parent group pages missing for {parent_group_label}")

    group = _find_group(parent_pages, group_label)
    if group is None:
        group = {}
        parent_pages.append(group)

    group.clear()
    group["group"] = group_label
    group["openapi"] = {
        "source": openapi_source_ref,
        "directory": openapi_directory,
    }
    group["pages"] = [*openapi_page_refs, details_page_ref]
    docs_json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def remove_legacy_output(*, output_file: Path) -> None:
    if output_file.exists():
        output_file.unlink()
        print(f"Removed legacy output: {output_file}")


def missing_operation_summaries(spec: dict[str, Any]) -> set[tuple[str, str]]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return set()

    missing: set[tuple[str, str]] = set()
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            summary = operation.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                missing.add((path, method.lower()))
    return missing


def openapi_operation_page_refs(spec: dict[str, Any]) -> list[str]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return []

    refs: list[str] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            refs.append(f"{method.upper()} {path}")
    return refs


def generated_operation_summary(path: str, method: str) -> str:
    mintlify_path = re.sub(r"\{([^{}]+)\}", r":\1", path)
    return f"{method.upper()} {mintlify_path}"


def path_only_operation_summary(path: str, method: str, summary: str) -> bool:
    normalized = summary.strip()
    if normalized == generated_operation_summary(path, method):
        return False
    return normalized in {
        path,
        re.sub(r"\{([^{}]+)\}", r":\1", path),
        f"{method.upper()} {path}",
    }


def operation_summary_rewrites(spec: dict[str, Any]) -> dict[tuple[str, str], str]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return {}

    rewrites: dict[tuple[str, str], str] = {}
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            summary = operation.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                rewrites[(path, method.lower())] = generated_operation_summary(path, method)
            elif path_only_operation_summary(path, method, summary):
                rewrites[(path, method.lower())] = generated_operation_summary(path, method)
    return rewrites


def add_missing_operation_summaries(text: str) -> str:
    spec = yaml.safe_load(text)
    if not isinstance(spec, dict):
        raise ValueError("Expected generated OpenAPI YAML to parse as an object")

    rewrites = operation_summary_rewrites(spec)
    if not rewrites:
        return text
    missing = missing_operation_summaries(spec)

    lines = text.splitlines()
    output_lines: list[str] = []
    in_paths = False
    paths_indent = ""
    current_path: str | None = None
    current_path_indent: str | None = None
    current_method: str | None = None
    current_method_indent: str | None = None

    for line in lines:
        if current_path is not None and current_method is not None and current_method_indent is not None:
            summary_match = re.fullmatch(rf"{re.escape(current_method_indent)}\s{{2}}summary:\s*.*", line)
            if summary_match and (current_path, current_method) in rewrites:
                summary_indent = f"{current_method_indent}  "
                output_lines.append(f'{summary_indent}summary: "{rewrites[(current_path, current_method)]}"')
                current_method = None
                current_method_indent = None
                continue

        output_lines.append(line)

        paths_match = re.fullmatch(r"(?P<indent>\s*)paths:\s*", line)
        if paths_match:
            in_paths = True
            paths_indent = paths_match.group("indent")
            current_path = None
            current_path_indent = None
            current_method = None
            current_method_indent = None
            continue

        if not in_paths:
            continue

        if line and not line.startswith(f"{paths_indent} "):
            in_paths = False
            current_path = None
            current_path_indent = None
            current_method = None
            current_method_indent = None
            continue

        path_match = re.fullmatch(rf"(?P<indent>{re.escape(paths_indent)}\s{{2}})(?P<path>/.*):\s*", line)
        if path_match:
            current_path = path_match.group("path")
            current_path_indent = path_match.group("indent")
            current_method = None
            current_method_indent = None
            continue

        if current_path is None or current_path_indent is None:
            continue

        method_match = re.fullmatch(
            rf"(?P<indent>{re.escape(current_path_indent)}\s{{2}})(?P<method>{'|'.join(sorted(HTTP_METHODS))}):\s*",
            line,
        )
        if method_match is None:
            continue

        method = method_match.group("method")
        current_method = method
        current_method_indent = method_match.group("indent")
        if (current_path, method) in missing:
            summary_indent = f"{method_match.group('indent')}  "
            output_lines.append(f'{summary_indent}summary: "{rewrites[(current_path, method)]}"')
            current_method = None
            current_method_indent = None

    rendered = "\n".join(output_lines).rstrip() + "\n"
    parsed = yaml.safe_load(rendered)
    if not isinstance(parsed, dict):
        raise ValueError("Generated OpenAPI YAML stopped parsing after summary insertion")
    remaining = operation_summary_rewrites(parsed)
    if remaining:
        details = ", ".join(f"{method.upper()} {path}" for path, method in sorted(remaining))
        raise ValueError(f"Failed to normalize generated summaries for OpenAPI operations: {details}")
    return rendered


def normalize_mintlify_operation_summaries(openapi_path: Path) -> None:
    original = openapi_path.read_text(encoding="utf-8")
    normalized = add_missing_operation_summaries(original)
    if normalized != original:
        openapi_path.write_text(normalized, encoding="utf-8")


def mintlify_openapi_page_refs(openapi_path: Path) -> list[str]:
    spec = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError(f"Expected generated OpenAPI YAML to parse as an object: {openapi_path}")
    return openapi_operation_page_refs(spec)


def operation_items(path_item: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (method.lower(), operation)
        for method, operation in path_item.items()
        if method.lower() in HTTP_METHODS and isinstance(operation, dict)
    ]


def operation_summary(path: str, path_item: dict[str, Any]) -> str:
    summaries: list[str] = []
    for method, operation in operation_items(path_item):
        summary = str(operation.get("summary") or "").strip()
        description = str(operation.get("description") or "").strip()
        label = summary if summary and summary not in {path, generated_operation_summary(path, method)} else description
        if label:
            summaries.append(f"{method.upper()}: {label}")
    if summaries:
        return compact_text("; ".join(summaries), limit=190)
    return "OpenAPI endpoint"


def operation_methods(path_item: dict[str, Any]) -> list[str]:
    return [method.upper() for method, _operation in operation_items(path_item)]


def path_item_fingerprint(path_item: Any) -> str:
    return json.dumps(path_item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def versioned_openapi_specs(
    *,
    source_config: dict[str, Any],
    cache_dir: Path,
    versions: list[dict[str, str]],
    spec_filename: str,
    force_refresh: bool,
) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for entry in versions:
        archive_path = ensure_bundle_archive(
            source_config=source_config,
            cache_dir=cache_dir,
            version_entry=entry,
            force_refresh=force_refresh,
        )
        spec = yaml.safe_load(
            add_missing_operation_summaries(
                read_bundle_spec_text(
                    archive_path,
                    source_config=source_config,
                    spec_filename=spec_filename,
                )
            )
        )
        if not isinstance(spec, dict):
            raise ValueError(f"Expected OpenAPI spec for {entry['version']} to parse as an object")
        specs[entry["version"]] = spec
    return specs


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


def build_openapi_details_page(
    *,
    specs_by_version: dict[str, dict[str, Any]],
    versions: list[str],
    publish_version: str,
    details_page_ref: str,
    source_name: str,
) -> Any:
    latest = specs_by_version[publish_version]
    latest_paths = latest.get("paths")
    if not isinstance(latest_paths, dict):
        raise ValueError("Published OpenAPI spec must define a paths object")

    version_path_items: dict[str, dict[str, Any]] = {}
    for version in versions:
        paths = specs_by_version[version].get("paths")
        version_path_items[version] = paths if isinstance(paths, dict) else {}

    endpoint_cards: list[ReferenceCard] = []
    version_cards: list[ReferenceCard] = []
    for path, path_item in latest_paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        present_versions = [
            version
            for version in versions
            if isinstance(version_path_items[version].get(path), dict)
        ]
        if not present_versions:
            continue
        introduced = present_versions[0]
        last_seen = present_versions[-1]
        changed_versions: list[str] = []
        previous_fingerprint: str | None = None
        for version in present_versions:
            fingerprint = path_item_fingerprint(version_path_items[version][path])
            if previous_fingerprint is not None and fingerprint != previous_fingerprint:
                changed_versions.append(version)
            previous_fingerprint = fingerprint

        badges = [
            ReferenceBadge(", ".join(operation_methods(path_item)) or "Endpoint", tone="protocol"),
            ReferenceBadge(f"Since {introduced}", tone="added"),
        ]
        if changed_versions:
            badges.append(ReferenceBadge(f"Changed {changed_versions[-1]}", tone="changed"))
        if any(bool(operation.get("deprecated")) for _method, operation in operation_items(path_item)):
            badges.append(ReferenceBadge("Deprecated", tone="removed"))
        endpoint_cards.append(
            ReferenceCard(
                title=path,
                summary=operation_summary(path, path_item),
                badges=badges,
                meta_items=[
                    ReferenceMetaItem("Operations", ", ".join(operation_methods(path_item)) or "-"),
                    ReferenceMetaItem("Last seen", last_seen),
                ],
            )
        )

    for version in versions:
        current_paths = version_path_items[version]
        previous_index = versions.index(version) - 1
        previous_paths = version_path_items[versions[previous_index]] if previous_index >= 0 else {}
        current_keys = {key for key, value in current_paths.items() if isinstance(key, str) and isinstance(value, dict)}
        previous_keys = {key for key, value in previous_paths.items() if isinstance(key, str) and isinstance(value, dict)}
        changed = sum(
            1
            for key in current_keys & previous_keys
            if path_item_fingerprint(current_paths[key]) != path_item_fingerprint(previous_paths[key])
        )
        version_cards.append(
            ReferenceCard(
                title=version,
                summary="Endpoint changes included in this release snapshot.",
                badges=[
                    ReferenceBadge(f"Added {len(current_keys - previous_keys)}", tone="added"),
                    ReferenceBadge(f"Changed {changed}", tone="changed"),
                    ReferenceBadge(f"Removed {len(previous_keys - current_keys)}", tone="removed"),
                ],
            )
        )

    return strip_raw_markdown_trailing_whitespace(
        render_collection_page(
            ReferenceCollectionPage(
                path=f"{details_page_ref}.mdx",
                title="Details and history",
                description="JSON Ledger API OpenAPI endpoint details and version history.",
                eyebrow="OpenAPI Reference",
                summary="Endpoint overview for the JSON Ledger API OpenAPI surface, built from versioned release snapshots.",
                badges=[ReferenceBadge("OpenAPI", tone="protocol"), ReferenceBadge(publish_version, tone="neutral")],
                meta_items=[
                    ReferenceMetaItem("Publish version", publish_version),
                    ReferenceMetaItem("Source", source_name),
                    ReferenceMetaItem("Version filter", ", ".join(versions)),
                ],
                sections=[
                    ReferenceSection(
                        heading="Endpoints",
                        body_markdown=safe_markdown_text(
                            "Select an OpenAPI operation from the sidebar for request and response details. "
                            "This page summarizes endpoint lifecycle changes across the configured Ledger API versions."
                        ),
                        cards=endpoint_cards,
                    ),
                    ReferenceSection(
                        heading="Version Summary",
                        cards=version_cards,
                    ),
                ],
            )
        )
    )


def write_openapi_details_page(
    *,
    docs_json_path: Path,
    details_page_ref: str,
    page: Any,
) -> None:
    write_page(page, docs_json_path.parent / f"{details_page_ref}.mdx")


def main() -> int:
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    include_versions = set(args.version) if args.version else None
    versions = selected_versions(source_config, include_versions)
    publish_entry = resolve_publish_version(
        source_config=source_config,
        versions=versions,
        requested_version=args.publish_version,
    )

    output_spec = Path(args.output_spec).resolve()
    cache_dir = Path(args.cache_dir).resolve()
    materialize_bundle_spec(
        source_config=source_config,
        cache_dir=cache_dir,
        version_entry=publish_entry,
        spec_filename="openapi.yaml",
        output_path=output_spec,
        force_refresh=args.force_refresh,
    )
    normalize_mintlify_operation_summaries(output_spec)
    print(f"Published Mintlify OpenAPI source: {output_spec}")

    docs_json_path = Path(args.docs_json).resolve()
    reference_nav.regroup_ledger_api_nav(
        docs_json_path=docs_json_path,
        dropdown_label=args.nav_dropdown,
    )
    update_docs_navigation(
        docs_json_path=docs_json_path,
        dropdown_label=args.nav_dropdown,
        parent_group_label=args.parent_group,
        group_label=args.group_label,
        openapi_source_ref=docs_relative_file_ref(output_spec, docs_json_path),
        openapi_directory=args.openapi_directory,
        details_page_ref=args.details_page_ref,
        openapi_page_refs=mintlify_openapi_page_refs(output_spec),
    )
    specs_by_version = versioned_openapi_specs(
        source_config=source_config,
        cache_dir=cache_dir,
        versions=versions,
        spec_filename="openapi.yaml",
        force_refresh=args.force_refresh,
    )
    write_openapi_details_page(
        docs_json_path=docs_json_path,
        details_page_ref=args.details_page_ref,
        page=build_openapi_details_page(
            specs_by_version=specs_by_version,
            versions=[entry["version"] for entry in versions],
            publish_version=publish_entry["version"],
            details_page_ref=args.details_page_ref,
            source_name=str(source_config.get("source") or "Canton release bundle JSON Ledger API OpenAPI fixtures"),
        ),
    )
    remove_legacy_output(output_file=LEGACY_OUTPUT_FILE.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
