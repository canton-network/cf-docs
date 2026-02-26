#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compute first-seen deprecation version per module from multiple docs JSON files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-snapshot\.(\d{8})\.(\d+)$")
RC_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-rc(\d+)$")
STABLE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def extract_tagged_warning_messages(warns: Any, tag: str) -> list[str]:
    values: list[Any]
    if warns is None:
        values = []
    elif isinstance(warns, list):
        values = warns
    else:
        values = [warns]

    out: list[str] = []

    def append_texts(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                append_texts(item)
            return
        if node is None:
            return
        text = str(node).strip()
        if text:
            out.append(text)

    for entry in values:
        if not isinstance(entry, dict):
            continue
        if tag in entry:
            append_texts(entry[tag])

    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def version_sort_key(version: str) -> tuple[Any, ...]:
    if m := SNAPSHOT_VERSION_RE.fullmatch(version):
        major, minor, patch, yyyymmdd, seq = m.groups()
        return (0, int(major), int(minor), int(patch), 0, int(yyyymmdd), int(seq))
    if m := RC_VERSION_RE.fullmatch(version):
        major, minor, patch, rc = m.groups()
        return (0, int(major), int(minor), int(patch), 1, int(rc), 0)
    if m := STABLE_VERSION_RE.fullmatch(version):
        major, minor, patch = m.groups()
        return (0, int(major), int(minor), int(patch), 2, 0, 0)
    return (1, version)


def parse_version_json_inputs(values: list[str]) -> list[tuple[str, Path]]:
    pairs: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid --version-json '{value}'. Expected VERSION=/path/to/file.json")
        version, raw_path = value.split("=", 1)
        version = version.strip()
        path = Path(raw_path).expanduser()
        if not version:
            raise ValueError(f"Invalid --version-json '{value}'. Missing version.")
        if version in seen:
            raise ValueError(f"Duplicate version '{version}'.")
        seen.add(version)
        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {path}")
        pairs.append((version, path))
    return sorted(pairs, key=lambda item: version_sort_key(item[0]))


def load_modules(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError(f"Expected top-level list or object in {path}")
    return [item for item in payload if isinstance(item, dict)]


def compute_first_seen_map(version_jsons: list[tuple[str, Path]]) -> dict[str, str]:
    first_seen: dict[str, str] = {}
    for version, path in version_jsons:
        for module in load_modules(path):
            module_name = str(module.get("md_name", "")).strip()
            if not module_name or module_name in first_seen:
                continue
            deprecations = extract_tagged_warning_messages(module.get("md_warn"), "DeprecatedData")
            if deprecations:
                first_seen[module_name] = version
    return first_seen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version-json",
        action="append",
        required=True,
        help="Mapping in the form VERSION=/path/to/docs.json. Repeat for each version.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
        help="Output path for module->first deprecation version mapping JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version_jsons = parse_version_json_inputs(args.version_json)
    first_seen = compute_first_seen_map(version_jsons)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w", encoding="utf-8") as f:
        json.dump(first_seen, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Wrote module deprecation first-seen map: {args.output_json}")
    print(f"Modules with deprecations: {len(first_seen)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
