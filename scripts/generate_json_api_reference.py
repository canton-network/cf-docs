#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "config" / "x2mdx" / "ledger-api" / "manifest.json"
DEFAULT_OUTPUT_FILE = REPO_ROOT / "docs-main" / "appdev" / "reference" / "json-api-reference.mdx"
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


def main() -> int:
    args = parse_args()
    command = build_command(args)
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
