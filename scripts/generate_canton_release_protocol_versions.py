#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import cast

from canton_release_reference import (
    DEFAULT_RELEASE_REPO,
    ReleaseAsset,
    ensure_release_archive,
    extract_release,
    resolve_release_asset,
    run_reference_script,
)
from docs_env import ensure_repo_direnv


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "canton-release-reference"
DEFAULT_OUTPUT = (
    REPO_ROOT / "docs-main" / "release-notes" / "releases-and-versioning.mdx"
)
REFERENCE_SCRIPT = REPO_ROOT / "scripts" / "canton_release_protocol_versions.canton"
GENERATED_START = "{/* GENERATED_CANTON_RELEASE_PROTOCOL_VERSIONS_START */}"
GENERATED_END = "{/* GENERATED_CANTON_RELEASE_PROTOCOL_VERSIONS_END */}"
LF_GENERATED_START = "{/* GENERATED_CANTON_PROTOCOL_LF_VERSIONS_START */}"
LF_GENERATED_END = "{/* GENERATED_CANTON_PROTOCOL_LF_VERSIONS_END */}"
BETA_LEGEND = r"\* A trailing asterisk identifies a beta protocol version."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Canton release-to-protocol compatibility from a public release binary."
    )
    parser.add_argument("--release-repo", default=DEFAULT_RELEASE_REPO)
    parser.add_argument("--canton-tag")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reference-json", type=Path)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--docs-json")
    return parser.parse_args()


def load_rows(
    payload: object, key: str = "releaseVersionsToProtocolVersions"
) -> list[tuple[str, list[str]]]:
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        raise ValueError(f"Canton reference JSON must contain a {key} list")
    rows: list[tuple[str, list[str]]] = []
    for index, row in enumerate(payload[key]):
        if (
            not isinstance(row, list)
            or len(row) != 2
            or not isinstance(row[0], str)
            or not isinstance(row[1], list)
            or not row[1]
            or not all(isinstance(value, str) and value for value in row[1])
        ):
            raise ValueError(f"{key} row {index} is invalid")
        rows.append((row[0], cast(list[str], row[1])))
    return rows


def render_section(rows: list[tuple[str, list[str]]], *, asset: ReleaseAsset) -> str:
    lines = [
        GENERATED_START,
        "",
        (
            "{/* GENERATED_FROM "
            f'source="{DEFAULT_RELEASE_REPO}" ref="{asset.tag}" asset="{asset.name}" '
            f'digest="{asset.digest}" release_line_count="{len(rows)}" */}}'
        ),
        "",
        "## Canton Release and Protocol Compatibility",
        "",
        (
            f"The public Canton {asset.version} release reports the following protocol-version support by release line."
        ),
        "",
        "| Canton release | Supported protocol versions |",
        "| --- | --- |",
    ]
    lines.extend(f"| {release} | {', '.join(versions)} |" for release, versions in rows)
    lines.extend(
        [
            "",
            BETA_LEGEND,
            "",
            GENERATED_END,
        ]
    )
    return "\n".join(lines)


def render_lf_section(rows: list[tuple[str, list[str]]], *, asset: ReleaseAsset) -> str:
    lines = [
        LF_GENERATED_START,
        "",
        (
            "{/* GENERATED_FROM "
            f'source="{DEFAULT_RELEASE_REPO}" ref="{asset.tag}" asset="{asset.name}" '
            f'digest="{asset.digest}" protocol_version_count="{len(rows)}" */}}'
        ),
        "",
        "## Protocol and Daml-LF Compatibility",
        "",
        (
            f"The public Canton {asset.version} release reports which Daml-LF versions a "
            "participant accepts in commands submitted to a synchronizer running each "
            "protocol version."
        ),
        "",
        "| Protocol version | Supported Daml-LF versions |",
        "| --- | --- |",
    ]
    lines.extend(f"| {protocol} | {', '.join(versions)} |" for protocol, versions in rows)
    if any(protocol.endswith("*") for protocol, _ in rows):
        lines.extend(["", BETA_LEGEND])
    lines.extend(["", LF_GENERATED_END])
    return "\n".join(lines)


def replace_section(
    page: str,
    section: str,
    start_marker: str = GENERATED_START,
    end_marker: str = GENERATED_END,
) -> str:
    if start_marker in page:
        start = page.index(start_marker)
        end = page.index(end_marker, start) + len(end_marker)
        return page[:start].rstrip() + "\n\n" + section + "\n" + page[end:].lstrip()
    return page.rstrip() + "\n\n" + section + "\n"


def main() -> int:
    ensure_repo_direnv(
        repo_root=REPO_ROOT, script_path=Path(__file__).resolve(), argv=sys.argv[1:]
    )
    args = parse_args()
    asset = resolve_release_asset(release_repo=args.release_repo, tag=args.canton_tag)
    if args.reference_json:
        payload = json.loads(args.reference_json.read_text(encoding="utf-8"))
    else:
        archive_path = ensure_release_archive(
            asset=asset, cache_dir=args.cache_dir, force_refresh=args.force_refresh
        )
        distribution_root = extract_release(
            archive_path=archive_path,
            asset=asset,
            cache_dir=args.cache_dir,
            force_refresh=args.force_refresh,
        )
        payload = run_reference_script(
            distribution_root=distribution_root,
            script_path=REFERENCE_SCRIPT,
            cache_dir=args.cache_dir,
            cache_namespace="release-protocol-versions",
            asset=asset,
            force_refresh=args.force_refresh,
        )

    rows = load_rows(payload)
    lf_rows = load_rows(payload, "protocolVersionsToLfVersions")
    page = args.output.read_text(encoding="utf-8")
    page = replace_section(page, render_section(rows, asset=asset))
    page = replace_section(
        page,
        render_lf_section(lf_rows, asset=asset),
        LF_GENERATED_START,
        LF_GENERATED_END,
    )
    args.output.write_text(page, encoding="utf-8")
    print(
        f"Generated {len(rows)} Canton release/protocol rows and {len(lf_rows)} "
        f"protocol/Daml-LF rows from {asset.tag} in {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
