#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Print target path relative to base path using POSIX separators."""

from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: relative_posix_path.py <target_path> <base_path>", file=sys.stderr)
        return 2
    target_path, base_path = sys.argv[1], sys.argv[2]
    print(os.path.relpath(target_path, base_path).replace(os.sep, "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
