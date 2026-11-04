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
    latest_patch_tags_by_release_line,
    resolve_release_asset,
    run_reference_script,
)
from docs_env import ensure_repo_direnv


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "canton-release-reference"
DEFAULT_OUTPUT = (
    REPO_ROOT / "docs-main" / "appdev" / "deep-dives" / "external-signing-topology.mdx"
)
REFERENCE_SCRIPT = REPO_ROOT / "scripts" / "canton_topology_transaction_versions.canton"
GENERATED_START = "{/* GENERATED_CANTON_TOPOLOGY_VERSIONS_START */}"
GENERATED_END = "{/* GENERATED_CANTON_TOPOLOGY_VERSIONS_END */}"
TABLE_HEADER = "| Protocol Version | Topology Transaction Protobuf Version |"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate topology-transaction version mappings from a public Canton release binary."
    )
    parser.add_argument("--release-repo", default=DEFAULT_RELEASE_REPO)
    parser.add_argument("--canton-tag")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reference-json", type=Path)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--docs-json")
    return parser.parse_args()


def load_rows(payload: object) -> list[tuple[str, list[str]]]:
    key = "topologyTransactionProtocolVersionToProtobufVersions"
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
            raise ValueError(f"Topology-version row {index} is invalid")
        rows.append((row[0], cast(list[str], row[1])))
    return rows


def load_page_rows(page: str) -> list[tuple[str, list[str]]]:
    if TABLE_HEADER not in page:
        return []
    lines = page[page.index(TABLE_HEADER) :].splitlines()[2:]
    rows: list[tuple[str, list[str]]] = []
    for line in lines:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 2 or not cells[0].isdigit() or not cells[1]:
            raise ValueError(f"Existing topology-version row is invalid: {line!r}")
        rows.append((cells[0], [value.strip() for value in cells[1].split(",")]))
    return rows


def merge_rows(
    existing: list[tuple[str, list[str]]], current: list[tuple[str, list[str]]]
) -> list[tuple[str, list[str]]]:
    # Older releases drop protocol versions they no longer support; keep those rows.
    merged = dict(existing)
    merged.update(current)
    return sorted(merged.items(), key=lambda row: int(row[0]))


def render_table(rows: list[tuple[str, list[str]]], *, asset: ReleaseAsset) -> str:
    lines = [
        GENERATED_START,
        "",
        (
            "{/* GENERATED_FROM "
            f'source="{DEFAULT_RELEASE_REPO}" ref="{asset.tag}" asset="{asset.name}" '
            f'digest="{asset.digest}" protocol_version_count="{len(rows)}" */}}'
        ),
        "",
        TABLE_HEADER,
        "| --- | --- |",
    ]
    lines.extend(
        f"| {protocol_version} | {', '.join(protobuf_versions)} |"
        for protocol_version, protobuf_versions in rows
    )
    lines.extend(["", GENERATED_END])
    return "\n".join(lines)


def replace_table(page: str, table: str) -> str:
    if GENERATED_START in page:
        start = page.index(GENERATED_START)
        end = page.index(GENERATED_END, start) + len(GENERATED_END)
        return page[:start].rstrip() + "\n\n" + table + "\n\n" + page[end:].lstrip()

    start = page.index(TABLE_HEADER)
    lines = page[start:].splitlines(keepends=True)
    table_line_count = 0
    for line in lines:
        if not line.strip():
            break
        table_line_count += 1
    end = start + sum(len(line) for line in lines[:table_line_count])
    return page[:start].rstrip() + "\n\n" + table + "\n\n" + page[end:].lstrip()


def main() -> int:
    ensure_repo_direnv(
        repo_root=REPO_ROOT, script_path=Path(__file__).resolve(), argv=sys.argv[1:]
    )
    args = parse_args()
    tag = args.canton_tag or latest_patch_tags_by_release_line(
        release_repo=args.release_repo, line_count=1
    )[0]
    asset = resolve_release_asset(release_repo=args.release_repo, tag=tag)
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
            cache_namespace="topology-transaction-versions",
            asset=asset,
            force_refresh=args.force_refresh,
        )

    page = args.output.read_text(encoding="utf-8")
    current_rows = load_rows(payload)
    rows = merge_rows(load_page_rows(page), current_rows)
    args.output.write_text(
        replace_table(page, render_table(rows, asset=asset)), encoding="utf-8"
    )
    print(
        f"Generated {len(current_rows)} topology/protobuf mappings from {asset.tag} "
        f"({len(rows)} total) in {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
