#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import TypedDict

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
    REPO_ROOT / "docs-main" / "global-synchronizer" / "reference" / "canton-metrics.mdx"
)
REFERENCE_SCRIPT = REPO_ROOT / "scripts" / "canton_metrics_reference.canton"
# Canton registers some metrics only on demand; this flag makes it register all of them for docs.
METRICS_DOCS_ENVIRONMENT = {"GENERATE_METRICS_FOR_DOCS": ""}
GENERATED_START = "{/* GENERATED_CANTON_METRICS_START */}"
GENERATED_END = "{/* GENERATED_CANTON_METRICS_END */}"
NODE_SECTIONS = (
    ("participant", "Participant Metrics"),
    ("sequencer", "Sequencer Metrics"),
    ("mediator", "Mediator Metrics"),
)


class MetricItem(TypedDict):
    name: str
    summary: str
    description: str
    type: str
    qualification: str
    labels: dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Canton Metrics reference page from a public Canton release binary."
    )
    parser.add_argument("--release-repo", default=DEFAULT_RELEASE_REPO)
    parser.add_argument(
        "--canton-tag",
        help="Public Canton release tag. Defaults to the latest GitHub release.",
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--reference-json",
        type=Path,
        help="Use previously generated metrics JSON instead of downloading and running a Canton release.",
    )
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args()


def load_metric(value: object, *, node: str) -> MetricItem:
    if not isinstance(value, dict):
        raise ValueError(f"Expected {node} metric objects in the Canton metrics JSON")
    fields: dict[str, str] = {}
    for key in ("name", "summary", "description", "type", "qualification"):
        field = value.get(key)
        if not isinstance(field, str):
            raise ValueError(
                f"{node} metric {value.get('name')!r} is missing string field {key!r}"
            )
        fields[key] = field
    labels = value.get("labels")
    if not isinstance(labels, dict) or not all(
        isinstance(label, str) and isinstance(description, str)
        for label, description in labels.items()
    ):
        raise ValueError(f"{node} metric {fields['name']!r} has malformed labels")
    return MetricItem(
        name=fields["name"],
        summary=fields["summary"],
        description=fields["description"],
        type=fields["type"],
        qualification=fields["qualification"],
        labels=dict(labels),
    )


def load_metrics(payload: object) -> dict[str, list[MetricItem]]:
    metrics = payload.get("metrics") if isinstance(payload, dict) else None
    if not isinstance(metrics, dict):
        raise ValueError("Canton metrics JSON is missing its metrics object")
    loaded: dict[str, list[MetricItem]] = {}
    for node, _ in NODE_SECTIONS:
        items = metrics.get(node)
        if not isinstance(items, list) or not items:
            raise ValueError(f"Canton metrics JSON has no {node} metrics")
        loaded[node] = [load_metric(item, node=node) for item in items]
    return loaded


def unique_sorted(items: list[MetricItem]) -> list[MetricItem]:
    """Drop repeated (name, type) registrations and sort by name, as Canton's docs build does."""
    seen: set[tuple[str, str]] = set()
    unique: list[MetricItem] = []
    for item in items:
        key = (item["name"], item["type"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return sorted(unique, key=lambda item: item["name"])


def mdx_inline(text: str) -> str:
    text = " ".join(text.split())
    text = re.sub(r"`([^`<]+?) <([^`>]+)>`_", r"[\1](\2)", text)
    text = re.sub(r"``([^`]+)``", r"`\1`", text)
    return (
        text.replace("<", r"\<")
        .replace(">", r"\>")
        .replace("{", r"\{")
        .replace("}", r"\}")
    )


def render_metric(item: MetricItem) -> list[str]:
    # Canton marks labelled metrics with a trailing asterisk: they are only exported to Prometheus.
    title = mdx_inline(item["name"] + ("*" if item["labels"] else "")).replace(
        "*", r"\*"
    )
    lines = [
        f"### {title}",
        "",
        f"> - **Summary**: {mdx_inline(item['summary'])}".rstrip(),
        f"> - **Description**: {mdx_inline(item['description'])}".rstrip(),
        f"> - **Type**: {mdx_inline(item['type'])}".rstrip(),
        f"> - **Qualification**: {mdx_inline(item['qualification'])}".rstrip(),
    ]
    if item["labels"]:
        lines.append("> - **Labels**:")
        lines.extend(
            f">   - **{label}**: {mdx_inline(description)}".rstrip()
            for label, description in item["labels"].items()
        )
    return lines


def render_generated_block(
    metrics: dict[str, list[MetricItem]], *, asset: ReleaseAsset
) -> str:
    sections = {node: unique_sorted(metrics[node]) for node, _ in NODE_SECTIONS}
    counts = " ".join(
        f'{node}_metric_count="{len(sections[node])}"' for node, _ in NODE_SECTIONS
    )
    lines = [
        GENERATED_START,
        "",
        (
            "{/* GENERATED_FROM "
            f'source="{DEFAULT_RELEASE_REPO}" ref="{asset.tag}" asset="{asset.name}" '
            f'digest="{asset.digest}" {counts} */}}'
        ),
    ]
    for node, heading in NODE_SECTIONS:
        lines.extend(["", f"## {heading}"])
        for item in sections[node]:
            lines.append("")
            lines.extend(render_metric(item))
    lines.extend(["", GENERATED_END])
    return "\n".join(lines)


def replace_generated_block(page: str, block: str) -> str:
    start = page.find(GENERATED_START)
    end = page.find(GENERATED_END, start)
    if start == -1 or end == -1:
        raise ValueError(
            f"Canton metrics page is missing its {GENERATED_START} and {GENERATED_END} markers"
        )
    end += len(GENERATED_END)
    return page[:start].rstrip() + "\n\n" + block + "\n\n" + page[end:].lstrip()


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
            cache_namespace="metrics",
            asset=asset,
            force_refresh=args.force_refresh,
            environment_overrides=METRICS_DOCS_ENVIRONMENT,
        )

    metrics = load_metrics(payload)
    page = args.output.read_text(encoding="utf-8")
    args.output.write_text(
        replace_generated_block(page, render_generated_block(metrics, asset=asset)),
        encoding="utf-8",
    )
    print(f"Generated {args.output} from Canton {asset.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
