#!/usr/bin/env python3
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build a version-index JSON for daml-prim Prelude and render a unified MDX page."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.daml_docs_json_to_mdx import render_context, render_instance, render_type
except ModuleNotFoundError:
    # Supports direct execution: `python3 scripts/build_versioned_daml_prim_prelude.py ...`
    from daml_docs_json_to_mdx import render_context, render_instance, render_type


@dataclass(frozen=True)
class VersionInput:
    version: str
    json_path: Path


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_semantic(node: Any) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "referenceAnchor" or key.endswith("_anchor"):
                continue
            if key.endswith("_descr") or key.endswith("_warns"):
                continue
            out[key] = _normalize_semantic(value)
        return out
    if isinstance(node, list):
        return [_normalize_semantic(item) for item in node]
    return node


def _load_modules(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError(f"Expected top-level list in {path}, found {type(payload).__name__}")
    return [item for item in payload if isinstance(item, dict)]


def _module_by_name(modules: list[dict[str, Any]], module_name: str) -> dict[str, Any] | None:
    for module in modules:
        if str(module.get("md_name", "")) == module_name:
            return module
    return None


def _as_union(node: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(node, dict) or len(node) != 1:
        return ("Unknown", {})
    [(tag, payload)] = node.items()
    if not isinstance(payload, dict):
        return (str(tag), {})
    return (str(tag), payload)


def _normalize_doc_text(descr: Any) -> str:
    if descr is None:
        return ""
    if isinstance(descr, str):
        return descr.strip()
    if isinstance(descr, list):
        paragraphs: list[str] = []
        for paragraph in descr:
            if isinstance(paragraph, list):
                text = "\n".join(str(item) for item in paragraph).strip()
            else:
                text = str(paragraph).strip()
            if text:
                paragraphs.append(text)
        return "\n\n".join(paragraphs)
    return str(descr).strip()


def _extract_deprecation_messages(warns: Any) -> list[str]:
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
        if "DeprecatedData" in entry:
            append_texts(entry["DeprecatedData"])

    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _extract_warning_messages(warns: Any) -> list[str]:
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
        if "WarnData" in entry:
            append_texts(entry["WarnData"])

    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _render_constructor(constructor: dict[str, Any]) -> dict[str, Any]:
    tag, payload = _as_union(constructor)
    name = str(payload.get("ac_name", ""))
    if tag == "RecordC":
        fields: list[dict[str, str]] = []
        for field in payload.get("ac_fields", []):
            if not isinstance(field, dict):
                continue
            fields.append(
                {
                    "name": str(field.get("fd_name", "")),
                    "type": render_type(field.get("fd_type")),
                    "description": _normalize_doc_text(field.get("fd_descr")),
                }
            )
        signature = name
    else:
        arg_types = [render_type(arg, 2) for arg in payload.get("ac_args", [])]
        signature = " ".join([name] + arg_types).strip()
        fields = []
    return {
        "kind": tag,
        "name": name,
        "signature": signature,
        "description": _normalize_doc_text(payload.get("ac_descr")),
        "fields": fields,
    }


def _build_function_state(module_name: str, fn: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    name = str(fn.get("fct_name", "")).strip()
    deprecations = _extract_deprecation_messages(fn.get("fct_warns"))
    signature = f"{name} : {render_context(fn.get('fct_context', []))}{render_type(fn.get('fct_type'))}"
    render_payload = {
        "signature": signature,
        "description": _normalize_doc_text(fn.get("fct_descr")),
        "deprecations": deprecations,
    }
    semantic_basis = {
        "fct_context": fn.get("fct_context", []),
        "fct_type": fn.get("fct_type"),
    }
    return (
        f"function:{module_name}.{name}",
        {
            "kind": "function",
            "module": module_name,
            "name": name,
            "render": render_payload,
            "semantic_hash": _stable_hash(_normalize_semantic(semantic_basis)),
            "deprecation_hash": _stable_hash(deprecations),
            "raw_hash": _stable_hash(fn),
            "raw": fn,
        },
    )


def _build_adt_state(module_name: str, adt_union: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    kind, adt = _as_union(adt_union)
    name = str(adt.get("ad_name", "")).strip()
    if not name:
        return None
    deprecations = _extract_deprecation_messages(adt.get("ad_warns"))

    args = [str(item) for item in adt.get("ad_args", [])]
    if kind == "TypeSynDoc":
        rhs = render_type(adt.get("ad_rhs"))
        declaration = f"type {name}{(' ' + ' '.join(args)) if args else ''} = {rhs}"
    else:
        declaration = f"data {name}{(' ' + ' '.join(args)) if args else ''}"

    constructors = [
        _render_constructor(constructor)
        for constructor in adt.get("ad_constrs", [])
        if isinstance(constructor, dict)
    ]
    instances = [render_instance(instance) for instance in adt.get("ad_instances", []) if isinstance(instance, dict)]

    render_payload = {
        "declaration": declaration,
        "description": _normalize_doc_text(adt.get("ad_descr")),
        "deprecations": deprecations,
        "constructors": constructors,
        "instances": instances,
    }
    semantic_basis = {
        "kind": kind,
        "ad_args": adt.get("ad_args", []),
        "ad_rhs": adt.get("ad_rhs"),
        "ad_constrs": adt.get("ad_constrs", []),
        "ad_instances": adt.get("ad_instances", []),
    }

    return (
        f"adt:{module_name}.{name}",
        {
            "kind": "adt",
            "module": module_name,
            "name": name,
            "render": render_payload,
            "semantic_hash": _stable_hash(_normalize_semantic(semantic_basis)),
            "deprecation_hash": _stable_hash(deprecations),
            "raw_hash": _stable_hash(adt_union),
            "raw": adt_union,
        },
    )


def _build_class_state(module_name: str, cls: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    class_name = str(cls.get("cl_name", "")).strip()
    if not class_name:
        return None
    deprecations = _extract_deprecation_messages(cls.get("cl_warns"))

    declaration = f"class {render_context(cls.get('cl_super', []))}{class_name}"
    if cls.get("cl_args"):
        declaration = f"{declaration} {' '.join(str(arg) for arg in cls.get('cl_args', []))}"
    methods: list[dict[str, str]] = []
    for method in cls.get("cl_methods", []):
        if not isinstance(method, dict):
            continue
        method_name = str(method.get("cm_name", "")).strip()
        signature = f"{method_name} : {render_context(method.get('cm_localContext', []))}{render_type(method.get('cm_type'))}"
        methods.append(
            {
                "name": method_name,
                "signature": signature,
                "description": _normalize_doc_text(method.get("cm_descr")),
            }
        )
    instances = [render_instance(instance) for instance in cls.get("cl_instances", []) if isinstance(instance, dict)]
    render_payload = {
        "declaration": declaration,
        "description": _normalize_doc_text(cls.get("cl_descr")),
        "deprecations": deprecations,
        "methods": methods,
        "instances": instances,
    }
    semantic_basis = {
        "cl_args": cls.get("cl_args", []),
        "cl_super": cls.get("cl_super", []),
        "cl_methods": cls.get("cl_methods", []),
    }
    return (
        f"class:{module_name}.{class_name}",
        {
            "kind": "class",
            "module": module_name,
            "name": class_name,
            "render": render_payload,
            "semantic_hash": _stable_hash(_normalize_semantic(semantic_basis)),
            "deprecation_hash": _stable_hash(deprecations),
            "raw_hash": _stable_hash(cls),
            "raw": cls,
        },
    )


def _build_method_state(
    module_name: str, class_name: str, method: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    method_name = str(method.get("cm_name", "")).strip()
    if not method_name:
        return None
    deprecations = _extract_deprecation_messages(method.get("cm_warns"))
    signature = f"{method_name} : {render_context(method.get('cm_localContext', []))}{render_type(method.get('cm_type'))}"
    render_payload = {
        "parent_class": class_name,
        "signature": signature,
        "description": _normalize_doc_text(method.get("cm_descr")),
        "deprecations": deprecations,
    }
    semantic_basis = {
        "cm_globalContext": method.get("cm_globalContext", []),
        "cm_localContext": method.get("cm_localContext", []),
        "cm_type": method.get("cm_type"),
    }
    return (
        f"class_method:{module_name}.{class_name}.{method_name}",
        {
            "kind": "class_method",
            "module": module_name,
            "class_name": class_name,
            "name": method_name,
            "render": render_payload,
            "semantic_hash": _stable_hash(_normalize_semantic(semantic_basis)),
            "deprecation_hash": _stable_hash(deprecations),
            "raw_hash": _stable_hash(method),
            "raw": method,
        },
    )


def _collect_states(module_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    module_name = str(module_doc.get("md_name", ""))

    deprecations = _extract_deprecation_messages(module_doc.get("md_warn"))
    warnings = _extract_warning_messages(module_doc.get("md_warn"))
    module_render = {
        "description": _normalize_doc_text(module_doc.get("md_descr")),
        "deprecations": deprecations,
        "warnings": warnings,
    }
    states[f"module:{module_name}"] = {
        "kind": "module",
        "module": module_name,
        "name": module_name,
        "render": module_render,
        "semantic_hash": _stable_hash(True),
        "deprecation_hash": _stable_hash(deprecations),
        "raw_hash": _stable_hash(module_doc),
        "raw": module_doc,
    }

    for fn in module_doc.get("md_functions", []):
        if not isinstance(fn, dict):
            continue
        key, value = _build_function_state(module_name, fn)
        states[key] = value

    for adt_union in module_doc.get("md_adts", []):
        if not isinstance(adt_union, dict):
            continue
        payload = _build_adt_state(module_name, adt_union)
        if payload is None:
            continue
        key, value = payload
        states[key] = value

    for cls in module_doc.get("md_classes", []):
        if not isinstance(cls, dict):
            continue
        class_payload = _build_class_state(module_name, cls)
        if class_payload is None:
            continue
        class_key, class_value = class_payload
        states[class_key] = class_value
        class_name = class_value["name"]
        for method in cls.get("cl_methods", []):
            if not isinstance(method, dict):
                continue
            method_payload = _build_method_state(module_name, class_name, method)
            if method_payload is None:
                continue
            method_key, method_value = method_payload
            states[method_key] = method_value

    return states


def _build_timeline(
    ordered_versions: list[str], per_version: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    timeline: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    open_segment: dict[str, Any] | None = None
    previous_state: dict[str, Any] | None = None
    previous_version: str | None = None

    for version in ordered_versions:
        state = per_version[version]
        present = bool(state.get("present"))
        if not present:
            if previous_state and previous_state.get("present"):
                events.append(
                    {
                        "version": version,
                        "event": "removed",
                        "from_version": previous_version,
                    }
                )
            if open_segment is not None and previous_version is not None:
                open_segment["end_version"] = previous_version
                timeline.append(open_segment)
                open_segment = None
            previous_state = state
            previous_version = version
            continue

        if previous_state is None or not previous_state.get("present"):
            events.append({"version": version, "event": "introduced"})
        else:
            if previous_state["semantic_hash"] != state["semantic_hash"]:
                events.append(
                    {
                        "version": version,
                        "event": "semantic_changed",
                        "from_version": previous_version,
                    }
                )
            elif previous_state["deprecation_hash"] != state["deprecation_hash"]:
                events.append(
                    {
                        "version": version,
                        "event": "deprecation_changed",
                        "from_version": previous_version,
                    }
                )

        if (
            open_segment is None
            or open_segment["semantic_hash"] != state["semantic_hash"]
            or open_segment["deprecation_hash"] != state["deprecation_hash"]
        ):
            if open_segment is not None and previous_version is not None:
                open_segment["end_version"] = previous_version
                timeline.append(open_segment)
            open_segment = {
                "start_version": version,
                "end_version": version,
                "semantic_hash": state["semantic_hash"],
                "deprecation_hash": state["deprecation_hash"],
                "render": state["render"],
            }
        else:
            open_segment["end_version"] = version

        previous_state = state
        previous_version = version

    if open_segment is not None:
        timeline.append(open_segment)

    return timeline, events


def build_enriched_index(
    inputs: list[VersionInput], module_name: str
) -> dict[str, Any]:
    if len(inputs) < 2:
        raise ValueError("Provide at least two --version-json inputs.")

    versions: list[dict[str, Any]] = []
    version_state_maps: dict[str, dict[str, dict[str, Any]]] = {}

    for order, item in enumerate(inputs):
        modules = _load_modules(item.json_path)
        module_doc = _module_by_name(modules, module_name)
        data = item.json_path.read_bytes()
        versions.append(
            {
                "id": item.version,
                "order": order,
                "source_json": str(item.json_path),
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "source_size_bytes": len(data),
            }
        )
        if module_doc is None:
            version_state_maps[item.version] = {}
        else:
            version_state_maps[item.version] = _collect_states(module_doc)

    ordered_versions = [item.version for item in inputs]
    all_keys = sorted(
        {key for per_version in version_state_maps.values() for key in per_version.keys()}
    )

    elements: list[dict[str, Any]] = []
    for key in all_keys:
        first_state = None
        per_version: dict[str, dict[str, Any]] = {}
        present_versions: list[str] = []
        for version in ordered_versions:
            state = version_state_maps[version].get(key)
            if state is None:
                per_version[version] = {"present": False}
                continue
            if first_state is None:
                first_state = state
            per_version[version] = {
                "present": True,
                "semantic_hash": state["semantic_hash"],
                "deprecation_hash": state["deprecation_hash"],
                "raw_hash": state["raw_hash"],
                "render": state["render"],
                "raw": state["raw"],
            }
            present_versions.append(version)

        if first_state is None:
            continue

        timeline, events = _build_timeline(ordered_versions, per_version)
        introduced_in = present_versions[0] if present_versions else None
        removed_in = None
        if present_versions:
            last_present_index = ordered_versions.index(present_versions[-1])
            if last_present_index < len(ordered_versions) - 1:
                removed_in = ordered_versions[last_present_index + 1]

        changed_versions = sorted(
            {
                event["version"]
                for event in events
                if event["event"] in ("semantic_changed", "deprecation_changed")
            }
        )
        semantic_changed_versions = sorted(
            {event["version"] for event in events if event["event"] == "semantic_changed"}
        )
        deprecation_changed_versions = sorted(
            {event["version"] for event in events if event["event"] == "deprecation_changed"}
        )
        elements.append(
            {
                "id": key,
                "kind": first_state["kind"],
                "module": first_state["module"],
                "name": first_state["name"],
                "class_name": first_state.get("class_name"),
                "introduced_in": introduced_in,
                "removed_in": removed_in,
                "status": "active" if per_version[ordered_versions[-1]].get("present") else "removed",
                "changed_versions": changed_versions,
                "semantic_changed_versions": semantic_changed_versions,
                "deprecation_changed_versions": deprecation_changed_versions,
                "timeline": timeline,
                "events": events,
                "versions": per_version,
            }
        )

    kind_buckets = ("module", "function", "adt", "class", "class_method")
    summary: dict[str, dict[str, int]] = {}
    first_version = ordered_versions[0]
    for kind in kind_buckets:
        subset = [item for item in elements if item["kind"] == kind]
        summary[kind] = {
            "total": len(subset),
            "added_after_baseline": sum(1 for item in subset if item["introduced_in"] and item["introduced_in"] != first_version),
            "removed": sum(1 for item in subset if item["removed_in"] is not None),
            "semantic_changed": sum(1 for item in subset if bool(item["semantic_changed_versions"])),
            "deprecation_changed": sum(1 for item in subset if bool(item["deprecation_changed_versions"])),
        }

    return {
        "schema_version": "daml-prim-version-index/v2",
        "package": "daml-prim",
        "module": module_name,
        "versions": versions,
        "elements": elements,
        "summary": summary,
    }


def _render_event(event: dict[str, Any]) -> str:
    version = str(event.get("version"))
    kind = str(event.get("event"))
    from_version = event.get("from_version")
    if from_version:
        return f"- `{kind}` in `{version}` (from `{from_version}`)"
    return f"- `{kind}` in `{version}`"


def _render_signature(render_payload: dict[str, Any]) -> str:
    return str(render_payload.get("signature") or render_payload.get("declaration") or "").strip()


def _render_deprecations(render_payload: dict[str, Any]) -> list[str]:
    raw = render_payload.get("deprecations", [])
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _render_warnings(render_payload: dict[str, Any]) -> list[str]:
    raw = render_payload.get("warnings", [])
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _version_family(version: str | None) -> str:
    if not version:
        return "-"
    core = str(version).split("-", 1)[0]
    match = re.match(r"^(\d+)\.(\d+)\.", core)
    if match:
        return f"{match.group(1)}.{match.group(2)}.x"
    return str(version)


def render_unified_mdx(index: dict[str, Any]) -> str:
    module_name = str(index["module"])
    versions = index["versions"]
    version_ids = [str(item["id"]) for item in versions]
    first_version = version_ids[0]
    last_version = version_ids[-1]
    module_element = next(
        (item for item in index["elements"] if item.get("kind") == "module" and item.get("name") == module_name),
        None,
    )
    module_render_payload: dict[str, Any] = {}
    module_introduced = None
    module_introduced_family = "-"
    module_removed_in = None
    module_status = "active"
    module_alpha_warning = ""
    if module_element:
        module_introduced = module_element.get("introduced_in")
        module_introduced_family = _version_family(module_introduced)
        module_removed_in = module_element.get("removed_in")
        if module_removed_in:
            module_status = "removed"
        latest_module_state = module_element.get("versions", {}).get(last_version, {})
        if isinstance(latest_module_state, dict):
            payload = latest_module_state.get("render", {})
            if isinstance(payload, dict):
                module_render_payload = payload
        warning_messages = _render_warnings(module_render_payload)
        for message in warning_messages:
            if "alpha" in message.lower():
                module_alpha_warning = message
                break

    lines: list[str] = [
        "---",
        f'title: "{module_name} API Across Versions"',
        f'description: "Unified {module_name} API view with version-introduced and version-changed markers."',
        "---",
        "",
        f"# {module_name} API Across Versions",
        "",
        f"Compared versions: {', '.join(f'`{version}`' for version in version_ids)}",
        "",
    ]

    if module_element:
        lines.extend(
            [
                "## Module Snapshot",
                "",
                "<CardGroup cols={3}>",
                '<Card title="Lifecycle">',
                "Alpha (experimental)." if module_alpha_warning else "No alpha warning in compared versions.",
                "</Card>",
                '<Card title="Introduced">',
                f"`{module_introduced_family}`",
                f"First seen in `{module_introduced}`" if module_introduced else "First seen in `-`",
                "</Card>",
                '<Card title="Status">',
                f"`{module_status}`",
                f"Removed in `{module_removed_in}`" if module_removed_in else f"Present in latest `{last_version}`",
                "</Card>",
                "</CardGroup>",
                "",
            ]
        )
        if module_alpha_warning:
            lines.extend(["<Warning>", module_alpha_warning, "</Warning>", ""])

    lines.extend(
        [
        "## Summary",
        "",
        "| Kind | Total | Added After Baseline | Removed | Signature Changed | Deprecation Changed |",
        "| :--- | ----: | -------------------: | ------: | ----------------: | ------------------: |",
        ]
    )

    for kind in ("function", "adt", "class", "class_method"):
        stats = index["summary"][kind]
        lines.append(
            f"| {kind} | {stats['total']} | {stats['added_after_baseline']} | {stats['removed']} | {stats['semantic_changed']} | {stats['deprecation_changed']} |"
        )

    lines.extend(
        [
            "",
            "## Function Index",
            "",
            "| Function | Added In | Removed In | Signature Changed In | Deprecation Changed In |",
            "| :------- | :------- | :--------- | :------------------- | :---------------------- |",
        ]
    )

    functions = sorted(
        [item for item in index["elements"] if item["kind"] == "function"],
        key=lambda item: str(item["name"]).lower(),
    )
    for element in functions:
        semantic_changed = ", ".join(
            f"`{version}`" for version in element["semantic_changed_versions"]
        ) or "-"
        deprecation_changed = ", ".join(
            f"`{version}`" for version in element["deprecation_changed_versions"]
        ) or "-"
        removed = f"`{element['removed_in']}`" if element["removed_in"] else "-"
        lines.append(
            f"| `{element['name']}` | `{element['introduced_in']}` | {removed} | {semantic_changed} | {deprecation_changed} |"
        )

    lines.extend(
        [
            "",
            "## Detailed Elements",
            "",
            f"Baseline version: `{first_version}`",
            f"Latest version: `{last_version}`",
            "",
        ]
    )

    order_rank = {"function": 0, "adt": 1, "class": 2, "class_method": 3, "module": 4}
    ordered_elements = sorted(
        [item for item in index["elements"] if item["kind"] in ("function", "adt", "class")],
        key=lambda item: (
            order_rank.get(str(item["kind"]), 99),
            str(item.get("name", "")).lower(),
        ),
    )

    for element in ordered_elements:
        lines.append(f"### `{element['kind']} {element['name']}`")
        lines.append(f"- Added in: `{element['introduced_in']}`")
        lines.append(f"- Removed in: `{element['removed_in']}`" if element["removed_in"] else "- Removed in: `-`")
        lines.append(f"- Status: `{element['status']}`")
        if element["semantic_changed_versions"]:
            lines.append(
                f"- Signature changed in: {', '.join(f'`{version}`' for version in element['semantic_changed_versions'])}"
            )
        else:
            lines.append("- Signature changed in: `-`")
        if element["deprecation_changed_versions"]:
            lines.append(
                f"- Deprecation changed in: {', '.join(f'`{version}`' for version in element['deprecation_changed_versions'])}"
            )
        else:
            lines.append("- Deprecation changed in: `-`")
        if element["events"]:
            lines.append("- Events:")
            lines.extend([f"  {_render_event(event)}" for event in element["events"]])
        else:
            lines.append("- Events: none")

        change_events = [
            event
            for event in element["events"]
            if event.get("event") in ("semantic_changed", "deprecation_changed")
            and event.get("from_version")
        ]
        if change_events:
            lines.append("")
            lines.append("Change details:")
            for event in change_events:
                from_version = str(event["from_version"])
                to_version = str(event["version"])
                from_state = element["versions"].get(from_version, {})
                to_state = element["versions"].get(to_version, {})
                from_render = from_state.get("render") if isinstance(from_state, dict) else {}
                to_render = to_state.get("render") if isinstance(to_state, dict) else {}
                from_render = from_render if isinstance(from_render, dict) else {}
                to_render = to_render if isinstance(to_render, dict) else {}

                event_name = str(event.get("event"))
                if event_name == "semantic_changed":
                    before_sig = _render_signature(from_render)
                    after_sig = _render_signature(to_render)
                    lines.append(f"- Signature changed: `{from_version}` -> `{to_version}`")
                    if before_sig:
                        lines.extend([f"  - Before (`{from_version}`):", "```daml", before_sig, "```"])
                    if after_sig:
                        lines.extend([f"  - After (`{to_version}`):", "```daml", after_sig, "```"])
                elif event_name == "deprecation_changed":
                    before_dep = _render_deprecations(from_render)
                    after_dep = _render_deprecations(to_render)
                    lines.append(f"- Deprecation changed: `{from_version}` -> `{to_version}`")
                    lines.append(f"  - Before (`{from_version}`):")
                    if before_dep:
                        lines.extend([f"    - {message}" for message in before_dep])
                    else:
                        lines.append("    - (none)")
                    lines.append(f"  - After (`{to_version}`):")
                    if after_dep:
                        lines.extend([f"    - {message}" for message in after_dep])
                    else:
                        lines.append("    - (none)")

        latest_version_state = element["versions"][last_version]
        render_payload = latest_version_state.get("render")
        if render_payload:
            signature = _render_signature(render_payload)
            if signature:
                lines.extend(["", "```daml", str(signature), "```"])
            description = str(render_payload.get("description", "")).strip()
            if description:
                lines.extend(["", description])
            deprecations = render_payload.get("deprecations", [])
            if deprecations:
                lines.extend(["", "Deprecation notes:"])
                for message in deprecations:
                    lines.append(f"- {message}")

        lines.append("")
        lines.append("Timeline:")
        for segment in element["timeline"]:
            if segment["start_version"] == segment["end_version"]:
                window = segment["start_version"]
            else:
                window = f"{segment['start_version']} -> {segment['end_version']}"
            lines.append(f"- `{window}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build enriched Prelude version-index JSON and a unified MDX page."
    )
    parser.add_argument(
        "--version-json",
        action="append",
        required=True,
        help="Mapping in the form VERSION=/path/to/prim.json. Repeat for each version.",
    )
    parser.add_argument(
        "--module",
        default="Prelude",
        help="Module name to render. Default: Prelude",
    )
    parser.add_argument(
        "--output-data",
        type=Path,
        required=True,
        help="Output path for enriched JSON data.",
    )
    parser.add_argument(
        "--output-mdx",
        type=Path,
        required=True,
        help="Output path for rendered MDX page.",
    )
    return parser.parse_args()


def _parse_version_inputs(values: list[str]) -> list[VersionInput]:
    out: list[VersionInput] = []
    seen: set[str] = set()
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid --version-json '{value}'. Expected VERSION=/path/to/file.json")
        version, path = value.split("=", 1)
        version = version.strip()
        json_path = Path(path).expanduser()
        if not version:
            raise ValueError(f"Invalid --version-json '{value}'. Missing version.")
        if version in seen:
            raise ValueError(f"Duplicate version '{version}'.")
        seen.add(version)
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        out.append(VersionInput(version=version, json_path=json_path))
    return out


def main() -> int:
    args = parse_args()
    inputs = _parse_version_inputs(args.version_json)
    index = build_enriched_index(inputs=inputs, module_name=args.module)

    args.output_data.parent.mkdir(parents=True, exist_ok=True)
    args.output_mdx.parent.mkdir(parents=True, exist_ok=True)

    args.output_data.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    args.output_mdx.write_text(render_unified_mdx(index), encoding="utf-8")

    print(f"Wrote enriched JSON: {args.output_data}")
    print(f"Wrote unified MDX:   {args.output_mdx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
