#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
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
GENERATED_START = "{/* GENERATED_CANTON_RELEASE_PROTOCOL_VERSIONS_START */}"
GENERATED_END = "{/* GENERATED_CANTON_RELEASE_PROTOCOL_VERSIONS_END */}"
LF_GENERATED_START = "{/* GENERATED_CANTON_PROTOCOL_LF_VERSIONS_START */}"
LF_GENERATED_END = "{/* GENERATED_CANTON_PROTOCOL_LF_VERSIONS_END */}"
BETA_LEGEND = r"\* A trailing asterisk identifies a beta protocol version."
CARRIED_FORWARD_MARK = "†"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Canton release-to-protocol compatibility from a public release binary."
    )
    parser.add_argument("--release-repo", default=DEFAULT_RELEASE_REPO)
    parser.add_argument(
        "--canton-tag",
        help="Probe this release instead of the latest patch of the newest release line.",
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


@dataclass(frozen=True)
class LfRow:
    protocol_version: int
    beta: bool
    lf_versions: list[str]
    last_reported_by: str
    carried_forward: bool = False


def probed_lf_rows(rows: list[tuple[str, list[str]]], *, asset: ReleaseAsset) -> list[LfRow]:
    return [
        LfRow(
            protocol_version=int(label.removesuffix("*")),
            beta=label.endswith("*"),
            lf_versions=versions,
            last_reported_by=asset.tag,
        )
        for label, versions in rows
    ]


LF_SNIPPET_ROWS_START = "export const protocolLfVersions = ["
LF_SNIPPET_ROWS_END = "];"


def load_published_lf_rows(snippet: Path) -> list[LfRow]:
    """Read the rows the dashboard snippet last published.

    Carried-forward rows exist only in this snippet, so anything other than the format
    `render_lf_snippet` writes fails instead of silently dropping them.
    """
    if not snippet.is_file():
        return []
    lines = [line.strip() for line in snippet.read_text(encoding="utf-8").splitlines()]
    if LF_SNIPPET_ROWS_START not in lines or LF_SNIPPET_ROWS_END not in lines:
        raise ValueError(f"{snippet} does not contain the generated protocolLfVersions rows")
    start = lines.index(LF_SNIPPET_ROWS_START) + 1
    end = lines.index(LF_SNIPPET_ROWS_END, start)
    rows: list[LfRow] = []
    for number, line in enumerate(lines[start:end], start=start + 1):
        if not line:
            continue
        try:
            if not line.endswith(","):
                raise ValueError("missing trailing comma")
            entry = json.loads(line.removesuffix(","))
            rows.append(
                LfRow(
                    protocol_version=int(entry["protocolVersion"]),
                    beta=bool(entry["beta"]),
                    lf_versions=list(entry["lfVersions"]),
                    last_reported_by=str(entry.get("lastReportedBy", "")),
                    carried_forward=bool(entry.get("carriedForward", False)),
                )
            )
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f"{snippet}:{number}: unreadable protocolLfVersions row: {error}") from error
    if not rows:
        raise ValueError(f"{snippet} has no protocolLfVersions rows")
    return rows


def carry_forward_lf_rows(
    probed: list[LfRow], published: list[LfRow], *, asset: ReleaseAsset
) -> list[LfRow]:
    """Keep published stable rows the probed release no longer reports, newest first.

    Canton never changes a stable protocol version's interpretation config, so a stable row
    that the probed release still reports must match what was published.
    """
    rows = {row.protocol_version: row for row in probed}
    for previous in published:
        current = rows.get(previous.protocol_version)
        if current is None:
            if not previous.beta:
                rows[previous.protocol_version] = LfRow(
                    protocol_version=previous.protocol_version,
                    beta=False,
                    lf_versions=previous.lf_versions,
                    last_reported_by=previous.last_reported_by,
                    carried_forward=True,
                )
        elif not previous.beta and current.lf_versions != previous.lf_versions:
            reported_by = previous.last_reported_by or "the published table"
            raise ValueError(
                f"Protocol version {previous.protocol_version}: {reported_by} reported "
                f"{previous.lf_versions} but {asset.tag} reports {current.lf_versions}"
            )
    return [rows[protocol] for protocol in sorted(rows, reverse=True)]


def lf_row_label(row: LfRow) -> str:
    beta = "*" if row.beta else ""
    carried = f" {CARRIED_FORWARD_MARK}" if row.carried_forward else ""
    return f"{row.protocol_version}{beta}{carried}"


def carried_forward_legend(asset: ReleaseAsset) -> str:
    return (
        f"{CARRIED_FORWARD_MARK} Not supported by Canton {asset.version}. Listed as reported "
        "by the earlier Canton release that last supported it."
    )


def render_lf_section(rows: list[LfRow], *, asset: ReleaseAsset) -> str:
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
    lines.extend(f"| {lf_row_label(row)} | {', '.join(row.lf_versions)} |" for row in rows)
    legends = []
    if any(row.beta for row in rows):
        legends.append(BETA_LEGEND)
    if any(row.carried_forward for row in rows):
        legends.append(carried_forward_legend(asset))
    for legend in legends:
        lines.extend(["", legend])
    lines.extend(["", LF_GENERATED_END])
    return "\n".join(lines)


def render_lf_snippet(rows: list[LfRow], *, asset: ReleaseAsset) -> str:
    """Render the protocol/Daml-LF rows as MDX exports for the version dashboard."""
    source = {
        "cantonVersion": asset.version,
        "tag": asset.tag,
        "asset": asset.name,
        "digest": asset.digest,
    }
    entries = [
        {
            "protocolVersion": str(row.protocol_version),
            "beta": row.beta,
            "lfVersions": row.lf_versions,
            "lastReportedBy": row.last_reported_by,
            "carriedForward": row.carried_forward,
        }
        for row in rows
    ]
    lines = [f"export const protocolLfVersionsSource = {json.dumps(source)};", ""]
    lines.append(LF_SNIPPET_ROWS_START)
    lines.extend(f"  {json.dumps(entry)}," for entry in entries)
    lines.append(LF_SNIPPET_ROWS_END)
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
            cache_namespace="release-protocol-versions",
            asset=asset,
            force_refresh=args.force_refresh,
        )

    rows = load_rows(payload)
    lf_rows = carry_forward_lf_rows(
        probed_lf_rows(load_rows(payload, "protocolVersionsToLfVersions"), asset=asset),
        load_published_lf_rows(args.lf_snippet_output),
        asset=asset,
    )
    page = args.output.read_text(encoding="utf-8")
    page = replace_section(page, render_section(rows, asset=asset))
    page = replace_section(
        page,
        render_lf_section(lf_rows, asset=asset),
        LF_GENERATED_START,
        LF_GENERATED_END,
    )
    args.output.write_text(page, encoding="utf-8")
    args.lf_snippet_output.parent.mkdir(parents=True, exist_ok=True)
    args.lf_snippet_output.write_text(
        render_lf_snippet(lf_rows, asset=asset), encoding="utf-8"
    )
    carried = sum(row.carried_forward for row in lf_rows)
    print(
        f"Generated {len(rows)} Canton release/protocol rows and {len(lf_rows)} "
        f"protocol/Daml-LF rows ({carried} carried forward) from {asset.tag} in {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
