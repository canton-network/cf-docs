#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""List latest Daml SDK versions by major.minor family from GitHub releases."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Any

SNAPSHOT_VERSION_RE = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)-snapshot\.(\d{8})\.(\d+)(?:\.[A-Za-z0-9._-]+)?$"
)
RC_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-rc(\d+)$")
STABLE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
FAMILY_RE = re.compile(r"^(\d+)\.(\d+)$")


def parse_count(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid count: {raw}") from exc
    if value < 1:
        raise ValueError(f"Count must be >= 1, got: {value}")
    return value


def parse_families(raw: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        m = FAMILY_RE.fullmatch(token)
        if not m:
            raise ValueError(f"Invalid family '{token}'. Expected form MAJOR.MINOR, for example 3.4")
        family = (int(m.group(1)), int(m.group(2)))
        if family not in seen:
            out.append(family)
            seen.add(family)
    if not out:
        raise ValueError("At least one family is required")
    return out


def version_sort_key(version: str) -> tuple[Any, ...]:
    if m := SNAPSHOT_VERSION_RE.fullmatch(version):
        major, minor, patch, yyyymmdd, seq = m.groups()
        return (0, int(major), int(minor), int(patch), 0, int(yyyymmdd), int(seq), version)
    if m := RC_VERSION_RE.fullmatch(version):
        major, minor, patch, rc = m.groups()
        return (0, int(major), int(minor), int(patch), 1, int(rc), 0, version)
    if m := STABLE_VERSION_RE.fullmatch(version):
        major, minor, patch = m.groups()
        return (0, int(major), int(minor), int(patch), 2, 0, 0, version)
    return (1, version)


def version_family(version: str) -> tuple[int, int] | None:
    for regex in (SNAPSHOT_VERSION_RE, RC_VERSION_RE, STABLE_VERSION_RE):
        m = regex.fullmatch(version)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def fetch_release_versions(repo: str) -> list[str]:
    versions: list[str] = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repo}/releases?per_page=100&page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": "daml-docs-sync"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to query GitHub releases: {exc}") from exc
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected GitHub releases payload: expected list")
        if not payload:
            break
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            tag = str(entry.get("tag_name", "")).strip()
            if not tag:
                continue
            if tag.startswith("v"):
                tag = tag[1:]
            versions.append(tag)
        if len(payload) < 100:
            break
        page += 1
    return versions


def select_versions(
    versions: list[str],
    families: list[tuple[int, int]],
    count_per_family: int,
) -> tuple[list[str], list[str]]:
    by_family: dict[tuple[int, int], list[str]] = {family: [] for family in families}

    unique_versions = sorted(set(versions), key=version_sort_key, reverse=True)
    for version in unique_versions:
        family = version_family(version)
        if family is None or family not in by_family:
            continue
        by_family[family].append(version)

    selected: list[str] = []
    warnings: list[str] = []
    for major, minor in families:
        pool = by_family[(major, minor)]
        picked = pool[:count_per_family]
        if len(picked) < count_per_family:
            warnings.append(
                f"Requested {count_per_family} version(s) for {major}.{minor}.x but found {len(picked)}."
            )
        selected.extend(picked)
    return selected, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("count_per_family", help="How many latest versions to select per family.")
    parser.add_argument(
        "--families",
        default="3.4,3.3,3.2",
        help="Comma-separated major.minor families in priority order. Default: 3.4,3.3,3.2",
    )
    parser.add_argument(
        "--repo",
        default="digital-asset/daml",
        help="GitHub repository to query for releases. Default: digital-asset/daml",
    )
    args = parser.parse_args()

    try:
        count = parse_count(args.count_per_family)
        families = parse_families(args.families)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        versions = fetch_release_versions(args.repo)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    selected, warnings = select_versions(versions, families, count)

    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)

    if not selected:
        family_display = ", ".join(f"{major}.{minor}.x" for major, minor in families)
        print(f"No versions found for requested families: {family_display}", file=sys.stderr)
        return 1

    for version in selected:
        print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
