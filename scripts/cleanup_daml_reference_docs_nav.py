#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Clean up docs.json navigation for single-tree Daml Standard Library docs publishing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.daml_docs_json_to_mdx import get_navigation_dropdowns
except ModuleNotFoundError:
    # Supports direct execution: `python3 scripts/cleanup_daml_reference_docs_nav.py ...`
    from daml_docs_json_to_mdx import get_navigation_dropdowns


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-json", type=Path, required=True, help="Path to docs.json")
    parser.add_argument(
        "--remove-dropdown-name",
        default="Daml Reference Docs",
        help="Top-level dropdown to remove entirely.",
    )
    parser.add_argument(
        "--appdev-dropdown-name",
        default="App Development",
        help="Dropdown where legacy groups should be removed from each version.",
    )
    parser.add_argument(
        "--remove-legacy-group-name",
        default="Generated API Reference",
        help="Legacy group name to remove from App Development versions.",
    )
    return parser.parse_args()


def cleanup_navigation(
    docs_json_path: Path,
    remove_dropdown_name: str,
    appdev_dropdown_name: str,
    remove_legacy_group_name: str,
) -> tuple[int, int]:
    with docs_json_path.open("r", encoding="utf-8") as handle:
        docs_json = json.load(handle)

    dropdowns = get_navigation_dropdowns(docs_json, docs_json_path)

    before_len = len(dropdowns)
    dropdowns[:] = [
        section
        for section in dropdowns
        if not (isinstance(section, dict) and section.get("dropdown") == remove_dropdown_name)
    ]
    removed_dropdowns = before_len - len(dropdowns)

    removed_legacy_groups = 0
    for section in dropdowns:
        if not isinstance(section, dict) or section.get("dropdown") != appdev_dropdown_name:
            continue
        versions = section.get("versions")
        if not isinstance(versions, list):
            continue
        for version in versions:
            if not isinstance(version, dict):
                continue
            groups = version.get("groups")
            if not isinstance(groups, list):
                continue
            before = len(groups)
            version["groups"] = [
                group
                for group in groups
                if not (
                    isinstance(group, dict)
                    and str(group.get("group", "")) == remove_legacy_group_name
                )
            ]
            removed_legacy_groups += before - len(version["groups"])

    with docs_json_path.open("w", encoding="utf-8") as handle:
        json.dump(docs_json, handle, indent=2)
        handle.write("\n")

    return removed_dropdowns, removed_legacy_groups


def main() -> int:
    args = parse_args()
    removed_dropdowns, removed_legacy_groups = cleanup_navigation(
        docs_json_path=args.docs_json,
        remove_dropdown_name=args.remove_dropdown_name,
        appdev_dropdown_name=args.appdev_dropdown_name,
        remove_legacy_group_name=args.remove_legacy_group_name,
    )
    print(
        "Updated docs.json: "
        f"removed {removed_dropdowns} '{args.remove_dropdown_name}' dropdown(s), "
        f"removed {removed_legacy_groups} '{args.remove_legacy_group_name}' group(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
