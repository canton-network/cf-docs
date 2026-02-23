#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Update docs.json navigation for Daml Reference Docs from JSONL version entries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from daml_docs_json_to_mdx import update_daml_reference_docs_navigation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-json", type=Path, required=True, help="Path to docs.json")
    parser.add_argument(
        "--entries-jsonl",
        type=Path,
        required=True,
        help="JSONL containing one object per line: {'version': str, 'pages': [str, ...]}",
    )
    return parser.parse_args()


def load_entries(entries_jsonl: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    with entries_jsonl.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise ValueError("Each JSONL line must be an object")
            entries.append(parsed)
    return entries


def main() -> int:
    args = parse_args()
    version_entries = load_entries(args.entries_jsonl)
    removed, updated_existing = update_daml_reference_docs_navigation(
        docs_json_path=args.docs_json,
        version_entries=version_entries,
        dropdown_name="Daml Reference Docs",
        group_name="Daml Prim API",
        icon="book-open",
        remove_legacy_dropdown_name="App Development",
        remove_legacy_group_name="Generated API Reference",
    )
    action = "updated existing" if updated_existing else "created new"
    print(
        f"Updated docs.json: {action} 'Daml Reference Docs' dropdown with {len(version_entries)} version(s); "
        f"removed {removed} legacy App Development group(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
