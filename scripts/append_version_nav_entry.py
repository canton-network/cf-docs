#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Append one version navigation entry to a JSONL file from generated MDX output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

EXCLUDED_NAV_TARGETS = frozenset(
    {
        "index",
        "ghc-show-text",
        "ghc-tuple-check",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="SDK version (for example 3.4.10)")
    parser.add_argument("--nav-base", required=True, help="docs.json page path prefix for this version")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory containing generated .mdx files")
    parser.add_argument("--entries-jsonl", type=Path, required=True, help="JSONL file to append to")
    return parser.parse_args()


def collect_nav_targets(output_dir: Path) -> list[str]:
    targets = sorted(path.stem for path in output_dir.glob("*.mdx"))
    return [target for target in targets if target not in EXCLUDED_NAV_TARGETS]


def main() -> int:
    args = parse_args()
    targets = collect_nav_targets(args.output_dir)
    if not targets:
        raise SystemExit(f"No navigable .mdx pages found in {args.output_dir}")

    nav_base = args.nav_base.rstrip("/")
    pages = [f"{nav_base}/{target}" for target in targets]
    entry = {"version": args.version, "pages": pages}

    args.entries_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.entries_jsonl.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
