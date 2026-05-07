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
    load_json,
    materialize_bundle_spec,
    selected_versions,
)
import reference_nav


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
    navigation = payload.get("navigation")
    if not isinstance(navigation, dict):
        raise ValueError(f"docs.json missing navigation object: {docs_json_path}")

    dropdowns = navigation.get("dropdowns")
    if not isinstance(dropdowns, list):
        raise ValueError(f"docs.json navigation.dropdowns must be a list: {docs_json_path}")

    dropdown = next(
        (item for item in dropdowns if isinstance(item, dict) and item.get("dropdown") == dropdown_label),
        None,
    )
    if dropdown is None:
        raise ValueError(f"Dropdown not found in docs.json: {dropdown_label}")

    pages = dropdown.get("pages")
    if not isinstance(pages, list):
        raise ValueError(f"Dropdown does not expose a pages list: {dropdown_label}")

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


def add_missing_operation_summaries(text: str) -> str:
    spec = yaml.safe_load(text)
    if not isinstance(spec, dict):
        raise ValueError("Expected generated OpenAPI YAML to parse as an object")

    missing = missing_operation_summaries(spec)
    if not missing:
        return text

    lines = text.splitlines()
    output_lines: list[str] = []
    in_paths = False
    paths_indent = ""
    current_path: str | None = None
    current_path_indent: str | None = None

    for line in lines:
        output_lines.append(line)

        paths_match = re.fullmatch(r"(?P<indent>\s*)paths:\s*", line)
        if paths_match:
            in_paths = True
            paths_indent = paths_match.group("indent")
            current_path = None
            current_path_indent = None
            continue

        if not in_paths:
            continue

        if line and not line.startswith(f"{paths_indent} "):
            in_paths = False
            current_path = None
            current_path_indent = None
            continue

        path_match = re.fullmatch(rf"(?P<indent>{re.escape(paths_indent)}\s{{2}})(?P<path>/.*):\s*", line)
        if path_match:
            current_path = path_match.group("path")
            current_path_indent = path_match.group("indent")
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
        if (current_path, method) in missing:
            summary_indent = f"{method_match.group('indent')}  "
            output_lines.append(f'{summary_indent}summary: "{current_path}"')

    rendered = "\n".join(output_lines).rstrip() + "\n"
    parsed = yaml.safe_load(rendered)
    if not isinstance(parsed, dict):
        raise ValueError("Generated OpenAPI YAML stopped parsing after summary insertion")
    remaining = missing_operation_summaries(parsed)
    if remaining:
        details = ", ".join(f"{method.upper()} {path}" for path, method in sorted(remaining))
        raise ValueError(f"Failed to insert generated summaries for OpenAPI operations: {details}")
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
    materialize_bundle_spec(
        source_config=source_config,
        cache_dir=Path(args.cache_dir).resolve(),
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
    remove_legacy_output(output_file=LEGACY_OUTPUT_FILE.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
