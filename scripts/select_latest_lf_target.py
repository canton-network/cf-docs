#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Select the latest LF target directory from a damlc package-db root."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def select_latest_target(pkg_db_root: Path) -> str:
    entries = [p.name for p in pkg_db_root.iterdir() if p.is_dir()]
    numeric = [name for name in entries if re.fullmatch(r"\d+\.\d+", name)]
    if numeric:
        numeric.sort(key=lambda value: tuple(int(part) for part in value.split(".")))
        return numeric[-1]
    if not entries:
        raise ValueError(f"No LF target directories found under: {pkg_db_root}")
    return sorted(entries)[-1]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: select_latest_lf_target.py <pkg_db_root>", file=sys.stderr)
        return 2

    pkg_db_root = Path(sys.argv[1])
    if not pkg_db_root.is_dir():
        print(f"Package DB root not found: {pkg_db_root}", file=sys.stderr)
        return 1

    try:
        print(select_latest_target(pkg_db_root))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
