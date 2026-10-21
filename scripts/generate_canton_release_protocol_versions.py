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
    REPO_ROOT / "docs-main" / "release-notes" / "releases-and-versioning.mdx"
)
DEFAULT_LF_SNIPPET_OUTPUT = (
    REPO_ROOT / "docs-main" / "snippets" / "generated" / "protocol-lf-versions.mdx"
)
REFERENCE_SCRIPT = REPO_ROOT / "scripts" / "canton_release_protocol_versions.canton"
# Release lines before 3.6 have no InterpretationConfig; this script derives the same mapping
# from their engine mode.
LEGACY_LF_REFERENCE_SCRIPT = (
    REPO_ROOT / "scripts" / "canton_protocol_lf_versions_legacy.canton"
)
LEGACY_LF_RELEASE_LINES_BEFORE = (3, 6)
# Supported minor release lines: the latest and the one before it.
DEFAULT_RELEASE_LINE_COUNT = 2
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
    parser.add_argument(
        "--canton-tag",
        help="Probe only this release instead of the latest patch of each supported line.",
    )
    parser.add_argument(
        "--release-line-count", type=int, default=DEFAULT_RELEASE_LINE_COUNT
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--lf-snippet-output", type=Path, default=DEFAULT_LF_SNIPPET_OUTPUT
    )
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


def release_line(asset: ReleaseAsset) -> tuple[int, int]:
    major, minor, _ = (int(part) for part in asset.version.split("."))
    return major, minor


def merge_lf_rows(
    sources: list[tuple[ReleaseAsset, list[tuple[str, list[str]]]]],
) -> list[tuple[str, list[str]]]:
    """Merge per-release protocol/Daml-LF rows, newest protocol version first.

    Canton keeps a stable protocol version's interpretation config fixed, so release lines
    that support the same protocol version must agree on it.
    """
    merged: dict[int, tuple[str, list[str], str]] = {}
    for asset, rows in sources:
        for label, versions in rows:
            protocol = int(label.removesuffix("*"))
            if protocol not in merged:
                merged[protocol] = (label, versions, asset.tag)
                continue
            previous_label, previous_versions, previous_tag = merged[protocol]
            if previous_versions != versions:
                raise ValueError(
                    f"Protocol version {protocol}: {previous_tag} reports "
                    f"{previous_versions} but {asset.tag} reports {versions}"
                )
            if previous_label.endswith("*") and not label.endswith("*"):
                merged[protocol] = (label, versions, previous_tag)
    return [
        (label, versions)
        for _, (label, versions, _) in sorted(merged.items(), reverse=True)
    ]


def describe_releases(assets: list[ReleaseAsset]) -> str:
    noun = "release reports" if len(assets) == 1 else "releases report"
    return f"The public Canton {' and '.join(asset.version for asset in assets)} {noun}"


def render_lf_section(
    rows: list[tuple[str, list[str]]], *, assets: list[ReleaseAsset]
) -> str:
    lines = [
        LF_GENERATED_START,
        "",
        (
            "{/* GENERATED_FROM "
            f'source="{DEFAULT_RELEASE_REPO}" '
            f'refs="{" ".join(asset.tag for asset in assets)}" '
            f'assets="{" ".join(asset.name for asset in assets)}" '
            f'digests="{" ".join(asset.digest for asset in assets)}" '
            f'protocol_version_count="{len(rows)}" */}}'
        ),
        "",
        "## Protocol and Daml-LF Compatibility",
        "",
        (
            f"{describe_releases(assets)} which Daml-LF versions a participant accepts in "
            "commands submitted to a synchronizer running each protocol version."
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


def render_lf_snippet(
    rows: list[tuple[str, list[str]]], *, assets: list[ReleaseAsset]
) -> str:
    """Render the protocol/Daml-LF rows as MDX exports for the version dashboard."""
    source = {
        "releases": [
            {
                "cantonVersion": asset.version,
                "tag": asset.tag,
                "asset": asset.name,
                "digest": asset.digest,
            }
            for asset in assets
        ]
    }
    entries = [
        {
            "protocolVersion": protocol.removesuffix("*"),
            "beta": protocol.endswith("*"),
            "lfVersions": versions,
        }
        for protocol, versions in rows
    ]
    lines = [f"export const protocolLfVersionsSource = {json.dumps(source)};", ""]
    lines.append("export const protocolLfVersions = [")
    lines.extend(f"  {json.dumps(entry)}," for entry in entries)
    lines.append("];")
    return "\n".join(lines) + "\n"


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


def probe_release(
    asset: ReleaseAsset, *, script_path: Path, cache_namespace: str, args: argparse.Namespace
) -> object:
    archive_path = ensure_release_archive(
        asset=asset, cache_dir=args.cache_dir, force_refresh=args.force_refresh
    )
    distribution_root = extract_release(
        archive_path=archive_path,
        asset=asset,
        cache_dir=args.cache_dir,
        force_refresh=args.force_refresh,
    )
    return run_reference_script(
        distribution_root=distribution_root,
        script_path=script_path,
        cache_dir=args.cache_dir,
        cache_namespace=cache_namespace,
        asset=asset,
        force_refresh=args.force_refresh,
    )


def probe_lf_rows(
    asset: ReleaseAsset, *, args: argparse.Namespace
) -> list[tuple[str, list[str]]]:
    if release_line(asset) < LEGACY_LF_RELEASE_LINES_BEFORE:
        payload = probe_release(
            asset,
            script_path=LEGACY_LF_REFERENCE_SCRIPT,
            cache_namespace="protocol-lf-versions-legacy",
            args=args,
        )
    else:
        payload = probe_release(
            asset,
            script_path=REFERENCE_SCRIPT,
            cache_namespace="release-protocol-versions",
            args=args,
        )
    return load_rows(payload, "protocolVersionsToLfVersions")


def main() -> int:
    ensure_repo_direnv(
        repo_root=REPO_ROOT, script_path=Path(__file__).resolve(), argv=sys.argv[1:]
    )
    args = parse_args()
    tags = (
        [args.canton_tag]
        if args.canton_tag
        else latest_patch_tags_by_release_line(
            release_repo=args.release_repo, line_count=args.release_line_count
        )
    )
    assets = [resolve_release_asset(release_repo=args.release_repo, tag=tag) for tag in tags]
    # The newest release line provides the release-to-protocol history.
    asset = assets[0]
    if args.reference_json:
        payload = json.loads(args.reference_json.read_text(encoding="utf-8"))
        assets = [asset]
        lf_sources = [(asset, load_rows(payload, "protocolVersionsToLfVersions"))]
    else:
        payload = probe_release(
            asset,
            script_path=REFERENCE_SCRIPT,
            cache_namespace="release-protocol-versions",
            args=args,
        )
        lf_sources = [(asset, load_rows(payload, "protocolVersionsToLfVersions"))]
        lf_sources.extend(
            (older, probe_lf_rows(older, args=args)) for older in assets[1:]
        )

    rows = load_rows(payload)
    lf_rows = merge_lf_rows(lf_sources)
    page = args.output.read_text(encoding="utf-8")
    page = replace_section(page, render_section(rows, asset=asset))
    page = replace_section(
        page,
        render_lf_section(lf_rows, assets=assets),
        LF_GENERATED_START,
        LF_GENERATED_END,
    )
    args.output.write_text(page, encoding="utf-8")
    args.lf_snippet_output.parent.mkdir(parents=True, exist_ok=True)
    args.lf_snippet_output.write_text(
        render_lf_snippet(lf_rows, assets=assets), encoding="utf-8"
    )
    print(
        f"Generated {len(rows)} Canton release/protocol rows from {asset.tag} and "
        f"{len(lf_rows)} protocol/Daml-LF rows from {', '.join(tags)} in {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
