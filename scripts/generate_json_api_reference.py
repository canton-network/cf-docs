#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "config" / "x2mdx" / "ledger-api" / "manifest.json"
DEFAULT_OUTPUT_FILE = REPO_ROOT / "docs-main" / "reference" / "json-api-reference.mdx"
LEGACY_OUTPUT_FILE = REPO_ROOT / "docs-main" / "appdev" / "reference" / "json-api-reference.mdx"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
DEFAULT_SNAPSHOT_VERSIONS = ["3.4", "3.5"]
DEFAULT_NAV_GROUP = "Ledger API Endpoints"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Mintlify JSON API reference page from checked-in OpenAPI snapshots."
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to the x2mdx snapshot manifest.",
    )
    parser.add_argument(
        "--output-file",
        default=str(DEFAULT_OUTPUT_FILE),
        help="Path to the generated MDX page.",
    )
    parser.add_argument(
        "--docs-json",
        default=str(DEFAULT_DOCS_JSON),
        help="Path to the Mintlify docs.json file to update.",
    )
    parser.add_argument(
        "--root",
        default="published",
        help="Root prefix used in manifest source paths.",
    )
    parser.add_argument(
        "--include-spec-pattern",
        default=r"^json-ledger-api/openapi\.yaml$",
        help="Regex selecting the Ledger API spec inside the manifest.",
    )
    parser.add_argument(
        "--nav-dropdown",
        default="Reference",
        help="Top-level Mintlify dropdown to update.",
    )
    parser.add_argument(
        "--nav-group",
        action="append",
        help="Mintlify group path to update. Repeat for nested groups. Defaults to 'Ledger API Endpoints'.",
    )
    parser.add_argument(
        "--version",
        action="append",
        help="OpenAPI snapshot versions to include in the generated page. Repeat to override the defaults.",
    )
    parser.add_argument(
        "--source-name",
        default="docs.digitalasset.com JSON Ledger API OpenAPI fixtures",
        help="Source label embedded in generated content.",
    )
    parser.add_argument(
        "--version-filter",
        default="published docs major versions",
        help="Version-filter label embedded in generated content.",
    )
    return parser.parse_args()


def build_command(args: argparse.Namespace) -> list[str]:
    nav_groups = args.nav_group if args.nav_group is not None else [DEFAULT_NAV_GROUP]
    versions = args.version or DEFAULT_SNAPSHOT_VERSIONS

    command = [
        "x2mdx",
        "openapi",
        "build-api-pages-from-manifest",
        "--manifest",
        str(Path(args.manifest).resolve()),
        "--root",
        args.root,
        "--include-spec-pattern",
        args.include_spec_pattern,
        "--output-file",
        str(Path(args.output_file).resolve()),
        "--docs-json",
        str(Path(args.docs_json).resolve()),
        "--nav-dropdown",
        args.nav_dropdown,
        "--source-name",
        args.source_name,
        "--version-filter",
        args.version_filter,
    ]

    for version in versions:
        command.extend(["--version", version])

    for nav_group in nav_groups:
        command.extend(["--nav-group", nav_group])

    return command


def load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


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


def normalize_reference_dropdown(*, docs_json_path: Path) -> None:
    payload = load_json(docs_json_path)
    navigation = payload.get("navigation")
    if not isinstance(navigation, dict):
        raise ValueError(f"Expected docs.json navigation object in {docs_json_path}")
    dropdowns = navigation.get("dropdowns")
    if not isinstance(dropdowns, list):
        raise ValueError(f"Expected docs.json navigation.dropdowns list in {docs_json_path}")

    reference_dropdown = next(
        (item for item in dropdowns if isinstance(item, dict) and item.get("dropdown") == "Reference"),
        None,
    )
    if reference_dropdown is None:
        raise ValueError(f"Reference dropdown not found in {docs_json_path}")

    pages = reference_dropdown.get("pages")
    if not isinstance(pages, list):
        pages = []
        reference_dropdown["pages"] = pages

    groups = reference_dropdown.get("groups")
    if isinstance(groups, list):
        endpoint_group = next(
            (item for item in groups if isinstance(item, dict) and item.get("group") == DEFAULT_NAV_GROUP),
            None,
        )
        if endpoint_group is not None:
            groups = [item for item in groups if item is not endpoint_group]
            pages = [item for item in pages if not (isinstance(item, dict) and item.get("group") == DEFAULT_NAV_GROUP)]
            pages.insert(0, endpoint_group)
            reference_dropdown["pages"] = pages
            if groups:
                reference_dropdown["groups"] = groups
            else:
                reference_dropdown.pop("groups", None)

    docs_json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def remove_legacy_output(*, output_file: Path) -> None:
    legacy_output = LEGACY_OUTPUT_FILE.resolve()
    if output_file == legacy_output:
        return
    if legacy_output.exists():
        legacy_output.unlink()
        print(f"Removed legacy output: {legacy_output}")


def main() -> int:
    args = parse_args()
    command = build_command(args)
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode == 0:
        cleanup_legacy_docs_ref(docs_json_path=Path(args.docs_json).resolve())
        normalize_reference_dropdown(docs_json_path=Path(args.docs_json).resolve())
        remove_legacy_output(output_file=Path(args.output_file).resolve())
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
