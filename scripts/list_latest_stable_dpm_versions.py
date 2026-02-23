#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""List latest stable Daml SDK versions available from dpm."""

from __future__ import annotations

import json
import re
import subprocess
import sys


def parse_count(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid count: {raw}") from exc
    if value < 1:
        raise ValueError(f"Count must be >= 1, got: {value}")
    return value


def sort_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: list_latest_stable_dpm_versions.py <count>", file=sys.stderr)
        return 2

    try:
        count = parse_count(sys.argv[1])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        raw = subprocess.check_output(
            ["dpm", "version", "--all", "-o", "json"],
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"Failed to query dpm versions: {exc}", file=sys.stderr)
        return exc.returncode or 1

    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Failed to parse dpm version JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(entries, list):
        print("Unexpected dpm version payload: expected a JSON list", file=sys.stderr)
        return 1

    stable = {
        str(entry.get("version", ""))
        for entry in entries
        if isinstance(entry, dict)
        and re.fullmatch(r"\d+\.\d+\.\d+", str(entry.get("version", "")))
    }
    ordered = sorted(stable, key=sort_key, reverse=True)
    for version in ordered[:count]:
        print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
