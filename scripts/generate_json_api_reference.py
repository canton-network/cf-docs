#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

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
LEGACY_OUTPUT_FILE = REPO_ROOT / "docs-main" / "reference" / "json-api-reference.mdx"


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
    docs_json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def remove_legacy_output(*, output_file: Path) -> None:
    if output_file.exists():
        output_file.unlink()
        print(f"Removed legacy output: {output_file}")


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
    )
    remove_legacy_output(output_file=LEGACY_OUTPUT_FILE.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
