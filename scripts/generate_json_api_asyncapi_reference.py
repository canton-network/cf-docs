#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from ledger_api_release_bundles import (
    bundle_url,
    load_json,
    manifest_source_path,
    materialize_bundle_spec,
    selected_versions,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "ledger-api-asyncapi" / "source-artifacts.json"
DEFAULT_BUNDLE_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "ledger-api-bundles"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "ledger-api-asyncapi"
DEFAULT_MANIFEST = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "ledger-api-asyncapi" / "manifest.json"
DEFAULT_OUTPUT_FILE = REPO_ROOT / "docs-main" / "reference" / "json-api-asyncapi-reference.mdx"
LEGACY_OUTPUT_FILE = REPO_ROOT / "docs-main" / "appdev" / "reference" / "json-api-asyncapi-reference.mdx"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
DEFAULT_NAV_GROUP = "Ledger API Endpoints"
DEFAULT_NAV_PAGE_ORDER = [
    "reference/json-api-reference",
    "reference/json-api-asyncapi-reference",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch JSON Ledger API AsyncAPI snapshots from Canton release bundles, write an x2mdx manifest, and render the Mintlify page."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--bundle-cache-dir", default=str(DEFAULT_BUNDLE_CACHE_DIR))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--manifest-out", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-file", default=str(DEFAULT_OUTPUT_FILE))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--nav-dropdown", default="API Reference")
    parser.add_argument(
        "--nav-group",
        action="append",
        help="Mintlify group path to update. Repeat for nested groups. Defaults to 'Ledger API Endpoints'.",
    )
    parser.add_argument("--version", action="append", help="Explicit version to include. Repeat to limit generation.")
    parser.add_argument("--publish-version", help="Version whose websocket surface should be published.")
    parser.add_argument(
        "--source-name",
        default="Canton release bundle JSON Ledger API AsyncAPI fixtures",
        help="Source label embedded in generated content.",
    )
    parser.add_argument(
        "--version-filter",
        default="configured docs major versions from Canton release bundles",
        help="Version-filter label embedded in generated content.",
    )
    parser.add_argument(
        "--page-title",
        default="JSON API AsyncAPI Reference",
        help="Title to use for the generated page.",
    )
    parser.add_argument(
        "--page-description",
        default="JSON Ledger API WebSocket AsyncAPI reference and version history.",
        help="Description to use for the generated page.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Refresh cached Canton release bundles and local AsyncAPI snapshots before rendering.",
    )
    return parser.parse_args()


def write_manifest(
    *,
    source_config: dict[str, object],
    manifest_path: Path,
    cache_dir: Path,
    repo_root: Path,
    versions: list[dict[str, str]],
    publish_version: str,
) -> Path:
    source_path = manifest_source_path(source_config, "asyncapi.yaml")
    manifest_versions: list[dict[str, str]] = []
    for version_entry in versions:
        version = version_entry["version"]
        fixture_path = cache_dir / version / "asyncapi.yaml"
        if not fixture_path.exists():
            continue
        manifest_versions.append(
            {
                "version": version,
                "url": bundle_url(source_config, version_entry),
                "source_path": source_path,
                "fixture_path": str(fixture_path.resolve().relative_to(repo_root.resolve())),
            }
        )

    manifest = {
        "source": source_config.get("source") or "Canton release bundle JSON Ledger API AsyncAPI fixtures",
        "publish_version": publish_version,
        "versions": manifest_versions,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    return manifest_path


def docs_json_page_ref(path: Path, docs_json_path: Path) -> str:
    relative = path.resolve().relative_to(docs_json_path.resolve().parent)
    if relative.suffix != ".mdx":
        raise ValueError(f"Expected MDX file under docs root, got: {path}")
    return relative.with_suffix("").as_posix()


def prune_page_ref(node: object, page_ref: str) -> object | None:
    if isinstance(node, list):
        items: list[object] = []
        for item in node:
            pruned = prune_page_ref(item, page_ref)
            if pruned is not None:
                items.append(pruned)
        return items
    if isinstance(node, dict):
        updated = {key: prune_page_ref(value, page_ref) for key, value in node.items()}
        if updated.get("group") and not updated.get("pages") and not updated.get("groups"):
            return None
        return updated
    if isinstance(node, str) and node == page_ref:
        return None
    return node


def cleanup_legacy_docs_ref(*, docs_json_path: Path) -> None:
    legacy_ref = docs_json_page_ref(LEGACY_OUTPUT_FILE.resolve(), docs_json_path)
    payload = load_json(docs_json_path)
    cleaned = prune_page_ref(payload, legacy_ref)
    if not isinstance(cleaned, dict):
        raise ValueError(f"Expected cleaned docs.json object for {docs_json_path}")
    docs_json_path.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")


def _find_group(items: list[object], label: str) -> dict[str, object] | None:
    for item in items:
        if isinstance(item, dict) and item.get("group") == label:
            return item
    return None


def _merge_group_entries(target: dict[str, object], source: dict[str, object]) -> None:
    target_pages = target.setdefault("pages", [])
    if not isinstance(target_pages, list):
        target_pages = []
        target["pages"] = target_pages

    for item in source.get("pages", []):
        if isinstance(item, str):
            if item not in target_pages:
                target_pages.append(item)
            continue
        if isinstance(item, dict) and item.get("group"):
            existing = _find_group(target_pages, str(item["group"]))
            if existing is None:
                target_pages.append(item)
            else:
                _merge_group_entries(existing, item)

    source_groups = source.get("groups", [])
    if isinstance(source_groups, list):
        target_groups = target.setdefault("groups", [])
        if not isinstance(target_groups, list):
            target_groups = []
            target["groups"] = target_groups
        for group in source_groups:
            if not isinstance(group, dict) or not group.get("group"):
                continue
            existing = _find_group(target_groups, str(group["group"]))
            if existing is None:
                target_groups.append(group)
            else:
                _merge_group_entries(existing, group)


def normalize_nav_group_into_pages(*, docs_json_path: Path, dropdown_label: str, group_label: str) -> None:
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

    raw_groups = dropdown.get("groups", [])
    if not isinstance(raw_groups, list):
        return

    moved_groups: list[dict[str, object]] = []
    remaining_groups: list[object] = []
    for item in raw_groups:
        if isinstance(item, dict) and item.get("group") == group_label:
            moved_groups.append(item)
        else:
            remaining_groups.append(item)

    if not moved_groups:
        return

    if remaining_groups:
        dropdown["groups"] = remaining_groups
    else:
        dropdown.pop("groups", None)

    pages = dropdown.setdefault("pages", [])
    if not isinstance(pages, list):
        raise ValueError(f"docs.json dropdown.pages must be a list: {docs_json_path}")

    existing = _find_group(pages, group_label)
    if existing is None:
        existing = {"group": group_label, "pages": []}
        pages.append(existing)

    for group in moved_groups:
        _merge_group_entries(existing, group)

    existing_pages = existing.get("pages")
    if isinstance(existing_pages, list):
        reordered = [page for page in DEFAULT_NAV_PAGE_ORDER if page in existing_pages]
        reordered.extend(page for page in existing_pages if page not in reordered)
        existing["pages"] = reordered
    if existing.get("groups") == []:
        existing.pop("groups", None)

    docs_json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_command(args: argparse.Namespace, manifest_path: Path, publish_version: str, versions: list[str]) -> list[str]:
    nav_groups = args.nav_group if args.nav_group is not None else [DEFAULT_NAV_GROUP]
    command = [
        "x2mdx",
        "asyncapi",
        "build-api-pages-from-manifest",
        "--manifest",
        str(manifest_path),
        "--fixture-root",
        str(REPO_ROOT),
        "--output-file",
        str(Path(args.output_file).resolve()),
        "--docs-json",
        str(Path(args.docs_json).resolve()),
        "--nav-dropdown",
        args.nav_dropdown,
        "--publish-version",
        publish_version,
        "--source-name",
        args.source_name,
        "--version-filter",
        args.version_filter,
        "--page-title",
        args.page_title,
        "--page-description",
        args.page_description,
    ]
    for nav_group in nav_groups:
        command.extend(["--nav-group", nav_group])
    for version in versions:
        command.extend(["--version", version])
    return command


def remove_legacy_output(*, output_file: Path) -> None:
    legacy_output = LEGACY_OUTPUT_FILE.resolve()
    if output_file == legacy_output:
        return
    if legacy_output.exists():
        legacy_output.unlink()
        print(f"Removed legacy output: {legacy_output}")


def main() -> int:
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    selected_version_entries = selected_versions(source_config, set(args.version) if args.version else None)

    publish_version = args.publish_version or str(source_config.get("publish_version") or selected_version_entries[-1]["version"])
    if publish_version not in {entry["version"] for entry in selected_version_entries}:
        raise ValueError(f"Publish version '{publish_version}' is not selected")

    cache_dir = Path(args.cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    bundle_cache_dir = Path(args.bundle_cache_dir).resolve()

    for entry in selected_version_entries:
        output_path = cache_dir / entry["version"] / "asyncapi.yaml"
        materialize_bundle_spec(
            source_config=source_config,
            cache_dir=bundle_cache_dir,
            version_entry=entry,
            spec_filename="asyncapi.yaml",
            output_path=output_path,
            force_refresh=args.force_refresh,
        )

    manifest_path = write_manifest(
        source_config=source_config,
        manifest_path=Path(args.manifest_out).resolve(),
        cache_dir=cache_dir,
        repo_root=REPO_ROOT,
        versions=selected_version_entries,
        publish_version=publish_version,
    )

    command = build_command(
        args,
        manifest_path=manifest_path,
        publish_version=publish_version,
        versions=[entry["version"] for entry in selected_version_entries],
    )
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode == 0:
        docs_json_path = Path(args.docs_json).resolve()
        nav_groups = args.nav_group if args.nav_group is not None else [DEFAULT_NAV_GROUP]
        cleanup_legacy_docs_ref(docs_json_path=docs_json_path)
        if nav_groups:
            normalize_nav_group_into_pages(
                docs_json_path=docs_json_path,
                dropdown_label=args.nav_dropdown,
                group_label=nav_groups[0],
            )
        remove_legacy_output(output_file=Path(args.output_file).resolve())
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
