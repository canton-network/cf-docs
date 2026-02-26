#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build publish JSON enriched with removed modules and module lifecycle metadata."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-snapshot\.(\d{8})\.(\d+)$")
RC_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-rc(\d+)$")
STABLE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


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


def _module_name(module_doc: dict[str, Any]) -> str:
    return str(module_doc.get("md_name", "")).strip()


def build_publish_modules(
    version_jsons: list[tuple[str, Path]],
    publish_version: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str | None]]]:
    ordered_versions = [version for version, _ in version_jsons]
    if publish_version not in ordered_versions:
        raise ValueError(
            f"Publish version '{publish_version}' is not present in --version-json inputs: {ordered_versions}"
        )

    publish_index = ordered_versions.index(publish_version)
    scoped_versions = version_jsons[: publish_index + 1]

    # module_name -> {"versions": [..], "docs": {version: module_doc}}
    module_history: dict[str, dict[str, Any]] = {}
    modules_by_version: dict[str, list[dict[str, Any]]] = {}
    for version, path in scoped_versions:
        modules = load_modules(path)
        modules_by_version[version] = modules
        for module_doc in modules:
            name = _module_name(module_doc)
            if not name:
                continue
            history = module_history.setdefault(name, {"versions": [], "docs": {}})
            history["versions"].append(version)
            history["docs"][version] = module_doc

    publish_modules = modules_by_version[publish_version]
    merged_modules: list[dict[str, Any]] = []
    publish_names: set[str] = set()
    for module_doc in publish_modules:
        name = _module_name(module_doc)
        if not name:
            continue
        merged_modules.append(copy.deepcopy(module_doc))
        publish_names.add(name)

    lifecycle: dict[str, dict[str, str | None]] = {}
    for name, history in module_history.items():
        present_versions = list(history["versions"])
        introduced_in = present_versions[0]
        last_seen_in = present_versions[-1]
        removed_in: str | None = None
        status = "active" if publish_version in present_versions else "unknown"

        if status != "active":
            last_seen_index = ordered_versions.index(last_seen_in)
            for candidate in ordered_versions[last_seen_index + 1 : publish_index + 1]:
                if candidate not in present_versions:
                    removed_in = candidate
                    break
            if removed_in is not None:
                status = "removed"

        lifecycle[name] = {
            "introduced_in": introduced_in,
            "last_seen_in": last_seen_in,
            "removed_in": removed_in,
            "status": status,
        }

        if status == "removed" and name not in publish_names:
            module_doc = history["docs"][last_seen_in]
            merged_modules.append(copy.deepcopy(module_doc))
            publish_names.add(name)

    return merged_modules, lifecycle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version-json",
        action="append",
        required=True,
        help="Mapping in the form VERSION=/path/to/docs.json. Repeat for each version.",
    )
    parser.add_argument(
        "--publish-version",
        required=True,
        help="SDK version whose docs are being published.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
        help="Output path for merged publish modules JSON.",
    )
    parser.add_argument(
        "--output-lifecycle-json",
        type=Path,
        required=True,
        help="Output path for module lifecycle metadata JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version_jsons = parse_version_json_inputs(args.version_json)
    merged_modules, lifecycle = build_publish_modules(version_jsons, publish_version=args.publish_version)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w", encoding="utf-8") as f:
        json.dump(merged_modules, f, indent=2, ensure_ascii=False)
        f.write("\n")

    args.output_lifecycle_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_lifecycle_json.open("w", encoding="utf-8") as f:
        json.dump(lifecycle, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")

    removed_count = sum(1 for item in lifecycle.values() if item.get("status") == "removed")
    print(f"Wrote merged publish modules JSON: {args.output_json}")
    print(f"Wrote module lifecycle JSON: {args.output_lifecycle_json}")
    print(f"Modules in publish set: {len(merged_modules)}")
    print(f"Removed modules retained for historical reference: {removed_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
