#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import generate_splice_mintlify_openapi as splice_openapi


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPLICE_OPENAPI_SOURCE_CONFIG = (
    REPO_ROOT / "config" / "mintlify-openapi" / "splice-openapi" / "source-artifacts.json"
)


@dataclass(frozen=True)
class SourceUpdate:
    source: str
    path: Path
    field: str
    previous: str
    current: str


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def latest_splice_openapi_version(source_config: dict[str, Any]) -> str:
    releases = splice_openapi.selected_releases(
        source_config=source_config,
        include_versions=None,
    )
    return releases[-1]["version"]


def update_splice_openapi_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> SourceUpdate | None:
    source_config = load_json(source_config_path)
    latest_version = latest_splice_openapi_version(source_config)
    configured_version = source_config.get("publish_version")
    if not isinstance(configured_version, str) or not configured_version:
        raise ValueError(f"{source_config_path} must define non-empty publish_version")
    if configured_version == latest_version:
        return None

    update = SourceUpdate(
        source="Splice OpenAPI",
        path=source_config_path,
        field="publish_version",
        previous=configured_version,
        current=latest_version,
    )
    if not dry_run:
        source_config["publish_version"] = latest_version
        write_json(source_config_path, source_config)
    return update


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update committed generated-reference source pins to their latest source versions."
    )
    parser.add_argument(
        "--splice-openapi-source-config",
        type=Path,
        default=DEFAULT_SPLICE_OPENAPI_SOURCE_CONFIG,
        help=f"Splice OpenAPI source-artifacts config. Default: {DEFAULT_SPLICE_OPENAPI_SOURCE_CONFIG}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report updates without writing source config files.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with status 1 if any source pins are stale.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    updates = [
        update
        for update in [
            update_splice_openapi_source(
                source_config_path=args.splice_openapi_source_config.resolve(),
                dry_run=args.dry_run or args.check,
            )
        ]
        if update is not None
    ]

    if not updates:
        print("Generated reference source pins are up to date.")
        return 0

    for update in updates:
        action = "Would update" if args.dry_run or args.check else "Updated"
        print(
            f"{action} {update.source} {update.field}: "
            f"{update.previous} -> {update.current} ({update.path})"
        )
    if args.check:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
