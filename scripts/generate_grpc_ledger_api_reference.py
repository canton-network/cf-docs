#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import generate_canton_protobuf_history as canton_protobuf_history
import reference_nav
from x2mdx.protobuf.lifecycle import (
    build_endpoint_lifecycle,
    build_protobuf_history_report_from_sources,
    build_release_diffs,
)
from x2mdx.protobuf.render import build_pages
from x2mdx.protobuf.snapshots import load_protobuf_sources
from x2mdx.render import write_pages


DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "grpc-ledger-api-reference" / "source-artifacts.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "protobuf-history"
DEFAULT_MANIFEST = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "grpc-ledger-api-reference" / "manifest.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs-main" / "reference" / "grpc-ledger-api-reference"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
DEFAULT_REPO_DIR = DEFAULT_CACHE_DIR / "repos" / "canton"
GROUP_LABEL = "gRPC Ledger API Reference"
PACKAGE_GROUP_LABEL = "Packages"
DEFAULT_INSERT_AFTER_GROUP = "Ledger API Endpoints"
DEFAULT_SOURCE_NAME = "Canton Ledger API protobuf release bundles"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Canton release-bundle protobuf inputs, filter them to Ledger API packages, and render a gRPC Ledger API reference."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--manifest-out", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--nav-dropdown", default="API Reference")
    parser.add_argument("--nav-group", action="append")
    parser.add_argument("--insert-after-group", default=DEFAULT_INSERT_AFTER_GROUP)
    parser.add_argument("--repo-dir", default=str(DEFAULT_REPO_DIR))
    parser.add_argument("--version", action="append", help="Explicit version to include. Repeat to limit generation.")
    parser.add_argument("--min-version", help="Minimum stable version to include when auto-discovering tags.")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetching tags from origin before generation.")
    parser.add_argument("--force-refresh", action="store_true", help="Refresh cached protobuf bundles and descriptor images.")
    parser.add_argument(
        "--source-name",
        default=DEFAULT_SOURCE_NAME,
        help="Source label embedded in generated content.",
    )
    parser.add_argument(
        "--version-filter",
        help="Version-filter label embedded in generated content.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def package_prefixes(source_config: dict[str, Any]) -> tuple[str, ...]:
    configured = source_config.get("package_prefixes")
    if configured is None:
        return ("com.daml.ledger.api.v2",)
    if not isinstance(configured, list) or not all(isinstance(item, str) and item for item in configured):
        raise ValueError("Source config package_prefixes must be a list of non-empty strings")
    return tuple(configured)


def package_matches(package_name: str, *, prefixes: tuple[str, ...]) -> bool:
    return any(package_name.startswith(prefix) for prefix in prefixes)


def filter_snapshot(snapshot: dict[str, Any], *, prefixes: tuple[str, ...]) -> dict[str, Any]:
    packages = [
        copy.deepcopy(package)
        for package in snapshot["packages"]
        if package_matches(str(package["package"]), prefixes=prefixes)
    ]
    files = {
        key: copy.deepcopy(value)
        for key, value in snapshot["files"].items()
        if package_matches(str(value["package"]), prefixes=prefixes)
    }
    services = {
        key: copy.deepcopy(value)
        for key, value in snapshot["services"].items()
        if package_matches(str(value["package"]), prefixes=prefixes)
    }
    endpoints = {
        key: copy.deepcopy(value)
        for key, value in snapshot["endpoints"].items()
        if package_matches(str(value["package"]), prefixes=prefixes)
    }
    messages = {
        key: copy.deepcopy(value)
        for key, value in snapshot["messages"].items()
        if package_matches(str(value["package"]), prefixes=prefixes)
    }
    fields = {
        key: copy.deepcopy(value)
        for key, value in snapshot["fields"].items()
        if package_matches(str(value["package"]), prefixes=prefixes)
    }
    enums = {
        key: copy.deepcopy(value)
        for key, value in snapshot["enums"].items()
        if package_matches(str(value["package"]), prefixes=prefixes)
    }
    enum_values = {
        key: copy.deepcopy(value)
        for key, value in snapshot["enumValues"].items()
        if package_matches(str(value["package"]), prefixes=prefixes)
    }
    return {
        **snapshot,
        "packages": packages,
        "files": files,
        "services": services,
        "endpoints": endpoints,
        "messages": messages,
        "fields": fields,
        "enums": enums,
        "enumValues": enum_values,
        "stats": {
            "protoFiles": len(files),
            "packages": len(packages),
            "services": len(services),
            "endpoints": len(endpoints),
            "messages": len(messages),
            "fields": len(fields),
            "enums": len(enums),
            "enumValues": len(enum_values),
        },
    }


def build_filtered_report(
    manifest_path: Path,
    *,
    prefixes: tuple[str, ...],
    source_name: str,
    version_filter: str,
) -> dict[str, Any]:
    sources = load_protobuf_sources(manifest_path)
    report = build_protobuf_history_report_from_sources(
        sources,
        source_name=source_name,
        version_filter=version_filter,
    )
    releases = [
        {
            **copy.deepcopy(release),
            "snapshot": filter_snapshot(release["snapshot"], prefixes=prefixes),
        }
        for release in report["releases"]
    ]
    if not any(release["snapshot"]["packages"] for release in releases):
        selected = ", ".join(prefixes)
        raise ValueError(f"No protobuf packages matched the configured prefixes: {selected}")

    build_release_diffs(releases)
    endpoint_lifecycle = [
        copy.deepcopy(entry)
        for entry in build_endpoint_lifecycle(releases)
        if package_matches(str(entry["package"]), prefixes=prefixes)
    ]
    latest_snapshot = releases[-1]["snapshot"]
    return {
        "generatedAt": report["generatedAt"],
        "sourceName": source_name,
        "versionFilter": version_filter,
        "repo": copy.deepcopy(report["repo"]),
        "latestRelease": releases[-1]["tag"],
        "latestSnapshot": latest_snapshot,
        "releases": releases,
        "endpointLifecycle": endpoint_lifecycle,
    }


def replace_text(path: Path, replacements: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    updated = text
    for old, new in replacements:
        updated = updated.replace(old, new)
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def retitle_generated_pages(*, output_dir: Path) -> None:
    overview_path = output_dir / "index.mdx"
    if overview_path.exists():
        replace_text(
            overview_path,
            [
                ("Canton Protobuf History", GROUP_LABEL),
                (
                    'description: "Descriptor-backed protobuf API history grouped by package."',
                    'description: "Generated Ledger API gRPC reference grouped by package."',
                ),
                (
                    "This page is generated from local descriptor-image snapshots with source info.",
                    "This page is generated from published Canton protobuf release bundles and filtered to the Ledger API gRPC packages.",
                ),
            ],
        )
    packages_dir = output_dir / "packages"
    for package_page in sorted(packages_dir.glob("*.mdx")):
        replace_text(package_page, [("Canton Protobuf History", GROUP_LABEL)])


def build_nav_group(
    *,
    docs_json_path: Path,
    overview_path: Path,
    package_paths: list[Path],
) -> tuple[dict[str, Any], set[str]]:
    overview_ref = canton_protobuf_history.docs_json_page_ref(overview_path, docs_json_path)
    package_refs = [
        canton_protobuf_history.docs_json_page_ref(package_path, docs_json_path)
        for package_path in package_paths
    ]
    refs = {overview_ref, *package_refs}
    pages: list[Any] = [overview_ref]
    if package_refs:
        pages.append({"group": PACKAGE_GROUP_LABEL, "pages": package_refs})
    return {"group": GROUP_LABEL, "pages": pages}, refs


def insert_group(items: list[Any], *, group: dict[str, Any], after_group: str | None) -> None:
    if after_group:
        for index, item in enumerate(items):
            if isinstance(item, dict) and item.get("group") == after_group:
                items.insert(index + 1, group)
                return
    items.append(group)


def update_docs_navigation(
    *,
    docs_json_path: Path,
    dropdown_label: str,
    parent_groups: list[str],
    insert_after_group: str | None,
    overview_path: Path,
    package_paths: list[Path],
) -> None:
    docs = load_json(docs_json_path)
    navigation = docs.get("navigation")
    if not isinstance(navigation, dict):
        raise ValueError(f"docs.json navigation must be an object: {docs_json_path}")
    dropdowns = navigation.get("dropdowns")
    if not isinstance(dropdowns, list):
        raise ValueError(f"docs.json navigation.dropdowns must be a list: {docs_json_path}")
    dropdown = next((item for item in dropdowns if isinstance(item, dict) and item.get("dropdown") == dropdown_label), None)
    if dropdown is None:
        raise ValueError(f"Dropdown not found in docs.json: {dropdown_label}")
    pages = dropdown.get("pages")
    if not isinstance(pages, list):
        raise ValueError(f"Dropdown does not expose a pages list: {dropdown_label}")

    nav_group, generated_refs = build_nav_group(
        docs_json_path=docs_json_path,
        overview_path=overview_path,
        package_paths=package_paths,
    )
    dropdown["pages"] = canton_protobuf_history.prune_nav_items(
        pages,
        page_refs=generated_refs,
        group_labels={GROUP_LABEL},
    )
    target_pages = canton_protobuf_history.ensure_group_path(dropdown["pages"], parent_groups)
    insert_group(target_pages, group=nav_group, after_group=insert_after_group)
    docs_json_path.write_text(json.dumps(docs, indent=2) + "\n", encoding="utf-8")
    print(f"Updated docs navigation: {docs_json_path}")


def write_manifest(
    *,
    source_config: dict[str, Any],
    cache_dir: Path,
    manifest_path: Path,
    repo_dir: Path,
    include_versions: set[str] | None,
    min_version: str,
    skip_fetch: bool,
    force_refresh: bool,
) -> Path:
    repo_config = source_config.get("repo") if isinstance(source_config.get("repo"), dict) else {}
    remote = repo_config.get("remote")
    if not isinstance(remote, str) or not remote:
        raise ValueError("Source config must define repo.remote")
    bundle_proto_dir = source_config.get("bundle_proto_dir") or "protobuf"
    if not isinstance(bundle_proto_dir, str) or not bundle_proto_dir:
        raise ValueError("Source config must define bundle_proto_dir")

    repo_dir = canton_protobuf_history.ensure_repo(repo_dir, remote=remote, fetch=not skip_fetch)
    selected_tags = canton_protobuf_history.stable_tags(
        repo_dir,
        min_version=min_version,
        include_versions=include_versions,
    )
    if not selected_tags:
        raise ValueError("No stable Canton tags selected")

    releases: list[dict[str, Any]] = []
    for version, tag in selected_tags:
        archive_path = canton_protobuf_history.ensure_bundle_archive(
            source_config=source_config,
            version=version,
            output_path=canton_protobuf_history.bundle_archive_path(cache_dir, version),
            force_refresh=force_refresh,
        )
        protobuf_root = canton_protobuf_history.extract_archive(
            archive_path,
            extract_root=canton_protobuf_history.bundle_extract_root(cache_dir, version),
            bundle_proto_dir=bundle_proto_dir,
            force_refresh=force_refresh,
        )
        import_to_repo_path = canton_protobuf_history.import_to_repo_path_from_bundle(protobuf_root)
        if not import_to_repo_path:
            print(f"Skipping {tag}: no published owned protobuf files found")
            continue
        image_path = canton_protobuf_history.descriptor_image_path(cache_dir, version)
        if not image_path.exists() or force_refresh:
            canton_protobuf_history.compile_descriptor_image(protobuf_root, output_path=image_path)
        releases.append(
            {
                "version": version,
                "tag": tag,
                "date": canton_protobuf_history.release_date(repo_dir, tag),
                "descriptor_image_path": str(image_path.resolve()),
                "import_to_repo_path": import_to_repo_path,
            }
        )
    if not releases:
        raise ValueError("No protobuf releases were materialized")
    return canton_protobuf_history.write_manifest(
        source_config=source_config,
        releases=releases,
        manifest_path=manifest_path,
    )


def main() -> int:
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    prefixes = package_prefixes(source_config)
    include_versions = set(args.version) if args.version else None
    min_version = args.min_version or source_config.get("min_version") or "0.0.0"
    if not isinstance(min_version, str):
        raise ValueError("min_version must be a string")

    manifest_path = write_manifest(
        source_config=source_config,
        cache_dir=Path(args.cache_dir).resolve(),
        manifest_path=Path(args.manifest_out).resolve(),
        repo_dir=Path(args.repo_dir).resolve(),
        include_versions=include_versions,
        min_version=min_version,
        skip_fetch=args.skip_fetch,
        force_refresh=args.force_refresh,
    )

    version_filter = args.version_filter
    if not version_filter:
        if include_versions:
            version_filter = "selected Canton release bundles"
        else:
            version_filter = f"stable Canton release bundles >= {min_version}"

    report = build_filtered_report(
        manifest_path,
        prefixes=prefixes,
        source_name=args.source_name,
        version_filter=version_filter,
    )
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    root, pages = build_pages(report, output_dir=output_dir)
    written_paths = write_pages(pages, root)
    retitle_generated_pages(output_dir=output_dir)

    overview_path = output_dir / "index.mdx"
    package_paths = [root / page.path for page in pages[1:]]
    update_docs_navigation(
        docs_json_path=Path(args.docs_json).resolve(),
        dropdown_label=args.nav_dropdown,
        parent_groups=args.nav_group or [],
        insert_after_group=args.insert_after_group,
        overview_path=overview_path,
        package_paths=package_paths,
    )
    reference_nav.regroup_ledger_api_nav(
        docs_json_path=Path(args.docs_json).resolve(),
        dropdown_label=args.nav_dropdown,
    )
    print(f"Wrote {len(written_paths)} generated pages under {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
