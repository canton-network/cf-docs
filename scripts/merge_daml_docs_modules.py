#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Merge daml-stdlib and daml-prim docs JSON module lists.

damlc docs emits the same ``md_name`` for entities moved via ``-- | MOVE``
annotations (e.g. Prelude, DA.Exception, DA.Stack). A first-wins combine
drops the prim-side MOVE content; this merge concatenates list fields while
keeping stdlib scalars (description, anchor, warnings) when both exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

LIST_KEYS = (
    "md_adts",
    "md_classes",
    "md_functions",
    "md_instances",
    "md_interfaces",
    "md_templates",
)

SCALAR_KEYS = (
    "md_descr",
    "md_anchor",
    "md_warn",
)


def _copy_module(module: dict[str, Any]) -> dict[str, Any]:
    copied = dict(module)
    for key in LIST_KEYS:
        value = copied.get(key)
        if isinstance(value, list):
            copied[key] = list(value)
    return copied


def _extend_list_field(target: dict[str, Any], source: dict[str, Any], key: str) -> None:
    incoming = source.get(key)
    if not isinstance(incoming, list) or not incoming:
        return
    existing = target.get(key)
    if not isinstance(existing, list):
        target[key] = list(incoming)
        return
    existing.extend(incoming)


def _fill_missing_scalars(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in SCALAR_KEYS:
        current = target.get(key)
        if current not in (None, "", []):
            continue
        incoming = source.get(key)
        if incoming not in (None, "", []):
            target[key] = incoming


def merge_stdlib_and_prim_modules(
    stdlib_modules: list[Any],
    prim_modules: list[Any],
) -> list[dict[str, Any]]:
    """Merge module docs with stdlib-first ordering and same-name list concat."""
    by_name: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for module in list(stdlib_modules) + list(prim_modules):
        if not isinstance(module, dict):
            continue
        name = module.get("md_name")
        if not isinstance(name, str) or not name:
            continue
        if name not in by_name:
            by_name[name] = _copy_module(module)
            order.append(name)
            continue
        existing = by_name[name]
        for key in LIST_KEYS:
            _extend_list_field(existing, module, key)
        _fill_missing_scalars(existing, module)

    return [by_name[name] for name in order]


def merge_json_files(stdlib_path: Path, prim_path: Path, out_path: Path) -> int:
    stdlib_modules = json.loads(stdlib_path.read_text(encoding="utf-8"))
    prim_modules = json.loads(prim_path.read_text(encoding="utf-8"))
    if not isinstance(stdlib_modules, list) or not isinstance(prim_modules, list):
        raise SystemExit("Expected list JSON payloads for stdlib and prim.")

    combined = merge_stdlib_and_prim_modules(stdlib_modules, prim_modules)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(combined, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Combined modules: {len(combined)} "
        f"(stdlib={len(stdlib_modules)}, prim={len(prim_modules)}; "
        f"merged_name_collisions="
        f"{len(stdlib_modules) + len(prim_modules) - len(combined)})"
    )
    return len(combined)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stdlib_json", type=Path)
    parser.add_argument("prim_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args(argv)
    merge_json_files(args.stdlib_json, args.prim_json, args.output_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
