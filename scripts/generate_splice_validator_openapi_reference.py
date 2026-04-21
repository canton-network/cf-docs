#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from splice_openapi_release_bundles import render_reference


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "splice-validator-openapi" / "source-artifacts.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "splice-openapi"
DEFAULT_MANIFEST = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "splice-validator-openapi" / "manifest.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs-main" / "reference" / "splice-validator-openapi"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
DEFAULT_SOURCE_NAME = "Splice Validator OpenAPI specs from published decentralized-canton-sync release bundles"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download published decentralized-canton-sync OpenAPI bundles, materialize the validator-family specs, and render Mintlify pages."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--manifest-out", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--nav-dropdown", default="API Reference")
    parser.add_argument("--version", action="append", help="Explicit release version to include. Repeat to limit generation.")
    parser.add_argument("--min-version", help="Minimum release version to include.")
    parser.add_argument("--force-refresh", action="store_true", help="Refresh cached release bundles and extracted YAML fixtures.")
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


def main() -> int:
    args = parse_args()
    include_versions = set(args.version) if args.version else None
    version_filter = args.version_filter
    if not version_filter:
        if include_versions:
            version_filter = "selected decentralized-canton-sync OpenAPI releases"
        else:
            version_filter = f"stable decentralized-canton-sync OpenAPI releases >= {args.min_version or '0.5.10'}"

    render_reference(
        source_config_path=Path(args.source_config).resolve(),
        cache_dir=Path(args.cache_dir).resolve(),
        manifest_path=Path(args.manifest_out).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        docs_json_path=Path(args.docs_json).resolve(),
        dropdown_label=args.nav_dropdown,
        include_versions=include_versions,
        min_version_override=args.min_version,
        source_name=args.source_name,
        version_filter=version_filter,
        force_refresh=args.force_refresh,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
