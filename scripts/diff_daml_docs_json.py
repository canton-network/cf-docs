#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compare two damlc docs JSON files at semantic and schema levels."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_modules(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected top-level list in {path}, found {type(data).__name__}")
    modules: list[dict[str, Any]] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Expected module object at index {idx} in {path}")
        modules.append(item)
    return modules


def _as_union(node: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(node, dict) or len(node) != 1:
        return ("Unknown", {})
    [(tag, payload)] = node.items()
    if not isinstance(payload, dict):
        return (str(tag), {})
    return (str(tag), payload)


def _normalize_for_semantic(node: Any) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "referenceAnchor" or key.endswith("_anchor"):
                continue
            if key.endswith("_descr") or key.endswith("_warns"):
                continue
            out[key] = _normalize_for_semantic(value)
        return out
    if isinstance(node, list):
        return [_normalize_for_semantic(item) for item in node]
    return node


def _build_entity_maps(modules: list[dict[str, Any]]) -> dict[str, dict[Any, Any]]:
    maps: dict[str, dict[Any, Any]] = {
        "modules": {},
        "functions": {},
        "adts": {},
        "classes": {},
        "class_methods": {},
    }

    for module in modules:
        module_name = str(module.get("md_name", "")).strip()
        if not module_name:
            continue
        maps["modules"][module_name] = True

        for fn in module.get("md_functions", []):
            if not isinstance(fn, dict):
                continue
            fn_name = str(fn.get("fct_name", "")).strip()
            if not fn_name:
                continue
            maps["functions"][(module_name, fn_name)] = _normalize_for_semantic(
                {
                    "fct_context": fn.get("fct_context", []),
                    "fct_type": fn.get("fct_type"),
                }
            )

        for adt_union in module.get("md_adts", []):
            tag, adt = _as_union(adt_union)
            adt_name = str(adt.get("ad_name", "")).strip()
            if not adt_name:
                continue
            maps["adts"][(module_name, adt_name)] = _normalize_for_semantic(
                {
                    "kind": tag,
                    "ad_args": adt.get("ad_args", []),
                    "ad_constrs": adt.get("ad_constrs", []),
                    "ad_rhs": adt.get("ad_rhs"),
                    "ad_instances": adt.get("ad_instances", []),
                }
            )

        for cls in module.get("md_classes", []):
            if not isinstance(cls, dict):
                continue
            class_name = str(cls.get("cl_name", "")).strip()
            if not class_name:
                continue
            maps["classes"][(module_name, class_name)] = _normalize_for_semantic(
                {
                    "cl_args": cls.get("cl_args", []),
                    "cl_super": cls.get("cl_super", []),
                    "cl_methods": cls.get("cl_methods", []),
                }
            )
            for method in cls.get("cl_methods", []):
                if not isinstance(method, dict):
                    continue
                method_name = str(method.get("cm_name", "")).strip()
                if not method_name:
                    continue
                maps["class_methods"][(module_name, class_name, method_name)] = _normalize_for_semantic(
                    {
                        "cm_globalContext": method.get("cm_globalContext", []),
                        "cm_localContext": method.get("cm_localContext", []),
                        "cm_type": method.get("cm_type"),
                    }
                )

    return maps


def _key_to_text(key: Any) -> str:
    if isinstance(key, tuple):
        return ".".join(str(part) for part in key)
    return str(key)


def _compare_entity_map(old: dict[Any, Any], new: dict[Any, Any]) -> dict[str, list[str]]:
    old_keys = set(old.keys())
    new_keys = set(new.keys())
    common = old_keys & new_keys

    def _sorted_keys(keys: set[Any] | list[Any]) -> list[Any]:
        return sorted(keys, key=_key_to_text)

    changed = [key for key in _sorted_keys(common) if old[key] != new[key]]
    return {
        "added": [_key_to_text(key) for key in _sorted_keys(new_keys - old_keys)],
        "removed": [_key_to_text(key) for key in _sorted_keys(old_keys - new_keys)],
        "changed": [_key_to_text(key) for key in changed],
    }


def compute_semantic_diff(
    old_modules: list[dict[str, Any]], new_modules: list[dict[str, Any]]
) -> dict[str, dict[str, list[str]]]:
    old_maps = _build_entity_maps(old_modules)
    new_maps = _build_entity_maps(new_modules)
    return {
        entity: _compare_entity_map(old_maps[entity], new_maps[entity])
        for entity in ("modules", "functions", "adts", "classes", "class_methods")
    }


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _path_to_text(path: tuple[str, ...]) -> str:
    if not path:
        return "$"
    out = "$"
    for segment in path:
        if segment == "[]":
            out += "[]"
        else:
            out += f".{segment}"
    return out


def _collect_schema(
    node: Any,
    path: tuple[str, ...],
    types_by_path: dict[str, set[str]],
    object_keys_by_path: dict[str, set[str]],
) -> None:
    path_text = _path_to_text(path)
    types_by_path[path_text].add(_json_type_name(node))
    if isinstance(node, dict):
        object_keys_by_path[path_text].update(node.keys())
        for key, value in node.items():
            _collect_schema(value, path + (str(key),), types_by_path, object_keys_by_path)
    elif isinstance(node, list):
        for item in node:
            _collect_schema(item, path + ("[]",), types_by_path, object_keys_by_path)


def compute_schema_diff(
    old_modules: list[dict[str, Any]], new_modules: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    old_types: dict[str, set[str]] = defaultdict(set)
    new_types: dict[str, set[str]] = defaultdict(set)
    old_object_keys: dict[str, set[str]] = defaultdict(set)
    new_object_keys: dict[str, set[str]] = defaultdict(set)

    _collect_schema(old_modules, tuple(), old_types, old_object_keys)
    _collect_schema(new_modules, tuple(), new_types, new_object_keys)

    type_changes: list[dict[str, Any]] = []
    for path in sorted(set(old_types.keys()) | set(new_types.keys())):
        old_path_types = sorted(old_types.get(path, set()))
        new_path_types = sorted(new_types.get(path, set()))
        if old_path_types != new_path_types:
            type_changes.append(
                {
                    "path": path,
                    "old_types": old_path_types,
                    "new_types": new_path_types,
                }
            )

    key_changes: list[dict[str, Any]] = []
    for path in sorted(set(old_object_keys.keys()) | set(new_object_keys.keys())):
        old_keys = old_object_keys.get(path, set())
        new_keys = new_object_keys.get(path, set())
        added = sorted(new_keys - old_keys)
        removed = sorted(old_keys - new_keys)
        if added or removed:
            key_changes.append(
                {
                    "path": path,
                    "added_keys": added,
                    "removed_keys": removed,
                }
            )

    return {"type_changes": type_changes, "key_changes": key_changes}


def _file_metadata(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _print_semantic_diff(semantic: dict[str, dict[str, list[str]]], max_items: int) -> None:
    print("Semantic API diff")
    print("-----------------")
    for entity, payload in semantic.items():
        added = payload["added"]
        removed = payload["removed"]
        changed = payload["changed"]
        print(
            f"{entity}: +{len(added)} -{len(removed)} changed={len(changed)}"
        )
        if added:
            print(f"  added (sample): {added[:max_items]}")
        if removed:
            print(f"  removed (sample): {removed[:max_items]}")
        if changed:
            print(f"  changed (sample): {changed[:max_items]}")
    print()


def _print_schema_diff(schema: dict[str, list[dict[str, Any]]], max_items: int) -> None:
    type_changes = schema["type_changes"]
    key_changes = schema["key_changes"]

    print("Schema/format diff")
    print("------------------")
    print(f"type-changed paths: {len(type_changes)}")
    print(f"object key-set changes: {len(key_changes)}")
    if type_changes:
        print("type changes (sample):")
        for entry in type_changes[:max_items]:
            print(
                f"  {entry['path']}: old={entry['old_types']} new={entry['new_types']}"
            )
    if key_changes:
        print("object key changes (sample):")
        for entry in key_changes[:max_items]:
            print(
                f"  {entry['path']}: +{entry['added_keys']} -{entry['removed_keys']}"
            )
    print()


def run_diff(old_json: Path, new_json: Path, max_items: int) -> dict[str, Any]:
    old_modules = load_modules(old_json)
    new_modules = load_modules(new_json)

    old_meta = _file_metadata(old_json)
    new_meta = _file_metadata(new_json)
    byte_identical = old_meta["sha256"] == new_meta["sha256"]

    semantic = compute_semantic_diff(old_modules, new_modules)
    schema = compute_schema_diff(old_modules, new_modules)

    print("Raw file diff")
    print("-------------")
    print(f"old: {old_json}")
    print(
        f"  size={old_meta['size_bytes']} sha256={old_meta['sha256']}"
    )
    print(f"new: {new_json}")
    print(
        f"  size={new_meta['size_bytes']} sha256={new_meta['sha256']}"
    )
    print(f"byte-identical: {'yes' if byte_identical else 'no'}")
    print()

    _print_semantic_diff(semantic, max_items=max_items)
    _print_schema_diff(schema, max_items=max_items)

    return {
        "byte_identical": byte_identical,
        "semantic": semantic,
        "schema": schema,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diff two damlc docs JSON files. Reports both semantic API changes "
            "and schema/format differences."
        )
    )
    parser.add_argument("--old-json", required=True, type=Path, help="Baseline JSON file.")
    parser.add_argument("--new-json", required=True, type=Path, help="New JSON file.")
    parser.add_argument(
        "--max-items",
        type=int,
        default=20,
        help="Max sample items to print for each difference category.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_diff(args.old_json, args.new_json, max_items=args.max_items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
