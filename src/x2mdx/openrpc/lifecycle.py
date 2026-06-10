"""Build lifecycle metadata for OpenRPC specs across supplied snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import cast

import yaml

from x2mdx.openrpc.models import (
    OpenRpcDocument,
    OpenRpcMethodHistory,
    OpenRpcMethodLifecycle,
    OpenRpcMethodDetail,
    OpenRpcParamDetail,
    OpenRpcReport,
    OpenRpcResultDetail,
    OpenRpcSourceSnapshot,
    OpenRpcSpecLifecycle,
    OpenRpcValueDetail,
)
from x2mdx.types import JsonObject, JsonValue

REQUEST_SAMPLE_MAX_DEPTH = 4
REQUEST_SAMPLE_MAX_PROPERTIES = 8
OpenRpcDocumentIndex = dict[str, OpenRpcDocument]
OpenRpcVersionDocumentIndex = dict[str, OpenRpcDocumentIndex]
OpenRpcMethodDetailsByName = dict[str, OpenRpcMethodDetail]


def sha256_json(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def version_key(version: str) -> tuple[tuple[int, int | str], ...]:
    version_text = version[1:] if version.startswith("v") else version
    parts = re.split(r"[.\-+@]", version_text)
    key: list[tuple[int, int | str]] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return tuple(key)


def parse_openrpc(raw_text: str) -> OpenRpcDocument:
    obj = yaml.safe_load(raw_text)
    if not isinstance(obj, dict):
        raise ValueError("OpenRPC document is not an object")
    if "openrpc" not in obj:
        raise ValueError("Document does not contain top-level `openrpc` key")
    return cast(OpenRpcDocument, obj)


def slugify(value: str) -> str:
    output = value.lower()
    output = re.sub(r"[^a-z0-9]+", "-", output)
    output = re.sub(r"-{2,}", "-", output).strip("-")
    return output


def method_anchor(name: str) -> str:
    return f"method-{slugify(name)}"


def normalize_lifecycle_state(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"alpha", "beta", "stable", "deprecated"}:
        return normalized
    return None


def doc_lookup_key(source_path: str) -> str:
    return source_path.replace("\\", "/")


def build_version_doc_index(snapshots: list[OpenRpcSourceSnapshot]) -> OpenRpcVersionDocumentIndex:
    index: OpenRpcVersionDocumentIndex = {}
    for snapshot in snapshots:
        version_index = index.setdefault(snapshot.version, {})
        normalized = doc_lookup_key(snapshot.source_path)
        version_index[normalized] = snapshot.document
        version_index[Path(normalized).name] = snapshot.document
        version_index[snapshot.spec_id] = snapshot.document
    return index


def resolve_local_fragment(document: OpenRpcDocument, fragment: str) -> JsonValue | None:
    target = cast(JsonValue, document)
    for part in fragment.split("/"):
        if isinstance(target, dict) and part in target:
            target = target[part]
        else:
            return None
    return target


def resolve_ref(
    doc_index: OpenRpcDocumentIndex,
    current_source_path: str,
    node: JsonValue | None,
    *,
    max_depth: int = 8,
) -> JsonValue | None:
    current = node
    current_doc_key = doc_lookup_key(current_source_path)
    depth = 0
    while isinstance(current, dict) and "$ref" in current and depth < max_depth:
        ref = current["$ref"]
        if not isinstance(ref, str):
            break

        if ref.startswith("#/"):
            target = resolve_local_fragment(doc_index[current_doc_key], ref[2:])
            if target is None:
                break
            current = target
            depth += 1
            continue

        if "#/" not in ref:
            break

        document_ref, fragment = ref.split("#/", 1)
        candidate_keys = [document_ref, Path(document_ref).name]
        target_doc = next((doc_index[key] for key in candidate_keys if key in doc_index), None)
        if target_doc is None:
            break
        target = resolve_local_fragment(target_doc, fragment)
        if target is None:
            break
        current = target
        depth += 1
    return current


def ref_schema_name(node: JsonValue | None) -> str | None:
    if not isinstance(node, dict):
        return None
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return None
    if "#/components/schemas/" in ref:
        return ref.split("#/components/schemas/", 1)[1]
    return None


def object_schema_properties_and_required(
    doc_index: OpenRpcDocumentIndex,
    current_source_path: str,
    schema: JsonValue | None,
    *,
    max_depth: int = 6,
) -> tuple[JsonObject, set[str]]:
    if max_depth <= 0:
        return {}, set()

    resolved = resolve_ref(doc_index, current_source_path, schema)
    if not isinstance(resolved, dict):
        return {}, set()

    properties: JsonObject = {}
    required: set[str] = set()

    all_of = resolved.get("allOf")
    if isinstance(all_of, list):
        for item in all_of:
            item_properties, item_required = object_schema_properties_and_required(
                doc_index,
                current_source_path,
                item,
                max_depth=max_depth - 1,
            )
            properties.update(item_properties)
            required.update(item_required)

    raw_properties = resolved.get("properties")
    if isinstance(raw_properties, dict):
        properties.update(raw_properties)

    raw_required = resolved.get("required")
    if isinstance(raw_required, list):
        required.update(str(name) for name in raw_required if isinstance(name, str))

    return properties, required


def schema_required_field_names(doc_index: OpenRpcDocumentIndex, current_source_path: str, schema: JsonValue | None) -> list[str]:
    properties, required = object_schema_properties_and_required(doc_index, current_source_path, schema)
    if not required:
        return []
    known = sorted(name for name in required if name in properties)
    unknown = sorted(name for name in required if name not in properties)
    return [*known, *unknown]


def schema_brief(doc_index: OpenRpcDocumentIndex, current_source_path: str, schema: JsonValue | None) -> str:
    resolved = resolve_ref(doc_index, current_source_path, schema)
    if not isinstance(resolved, dict):
        return "-"
    type_name = resolved.get("type")
    if isinstance(type_name, str):
        if type_name == "array":
            return f"array[{schema_brief(doc_index, current_source_path, resolved.get('items'))}]"
        return type_name
    if isinstance(resolved.get("oneOf"), list):
        return "oneOf"
    if isinstance(resolved.get("anyOf"), list):
        return "anyOf"
    if isinstance(resolved.get("allOf"), list):
        return "allOf"
    if isinstance(resolved.get("properties"), dict):
        return "object"
    return "-"


def schema_type_token(doc_index: OpenRpcDocumentIndex, current_source_path: str, schema: JsonValue | None) -> JsonValue:
    resolved = resolve_ref(doc_index, current_source_path, schema)
    if not isinstance(resolved, dict):
        return "<value>"

    one_of = resolved.get("oneOf")
    if isinstance(one_of, list) and one_of:
        return schema_type_token(doc_index, current_source_path, one_of[0])

    any_of = resolved.get("anyOf")
    if isinstance(any_of, list) and any_of:
        return schema_type_token(doc_index, current_source_path, any_of[0])

    type_name = resolved.get("type")
    if type_name == "string":
        return "<string>"
    if type_name == "integer":
        return "<integer>"
    if type_name == "number":
        return "<number>"
    if type_name == "boolean":
        return "<boolean>"
    if type_name == "array":
        return [schema_type_token(doc_index, current_source_path, resolved.get("items"))]

    properties, _required = object_schema_properties_and_required(doc_index, current_source_path, resolved)
    if type_name == "object" or properties or isinstance(resolved.get("allOf"), list):
        return "<object>"
    return "<value>"


def schema_sample_value(
    doc_index: OpenRpcDocumentIndex,
    current_source_path: str,
    schema: JsonValue | None,
    *,
    max_depth: int = REQUEST_SAMPLE_MAX_DEPTH,
    max_properties: int = REQUEST_SAMPLE_MAX_PROPERTIES,
    required_only: bool = True,
) -> JsonValue:
    if max_depth <= 0:
        return schema_type_token(doc_index, current_source_path, schema)

    resolved = resolve_ref(doc_index, current_source_path, schema)
    if not isinstance(resolved, dict):
        return schema_type_token(doc_index, current_source_path, schema)

    one_of = resolved.get("oneOf")
    if isinstance(one_of, list) and one_of:
        return schema_sample_value(
            doc_index,
            current_source_path,
            one_of[0],
            max_depth=max_depth,
            max_properties=max_properties,
            required_only=required_only,
        )

    any_of = resolved.get("anyOf")
    if isinstance(any_of, list) and any_of:
        return schema_sample_value(
            doc_index,
            current_source_path,
            any_of[0],
            max_depth=max_depth,
            max_properties=max_properties,
            required_only=required_only,
        )

    properties, required = object_schema_properties_and_required(
        doc_index,
        current_source_path,
        resolved,
        max_depth=max_depth,
    )
    type_name = resolved.get("type")
    if type_name == "object" or properties or isinstance(resolved.get("allOf"), list):
        property_names = list(properties.keys())
        required_names = [name for name in property_names if name in required]
        unknown_required_names = sorted(name for name in required if name not in properties)
        names_to_render = required_names if required_only and required_names else property_names
        if not names_to_render and unknown_required_names:
            names_to_render = unknown_required_names

        sample: JsonObject = {}
        for name in names_to_render[:max_properties]:
            if name in properties:
                sample[name] = schema_sample_value(
                    doc_index,
                    current_source_path,
                    properties[name],
                    max_depth=max_depth - 1,
                    max_properties=max_properties,
                    required_only=required_only,
                )
            else:
                sample[name] = "<value>"
        return sample

    if type_name == "array":
        return [
            schema_sample_value(
                doc_index,
                current_source_path,
                resolved.get("items"),
                max_depth=max_depth - 1,
                max_properties=max_properties,
                required_only=required_only,
            )
        ]

    if type_name == "string":
        return "<string>"
    if type_name == "integer":
        return "<integer>"
    if type_name == "number":
        return "<number>"
    if type_name == "boolean":
        return "<boolean>"
    return schema_type_token(doc_index, current_source_path, resolved)


def extract_param_detail(
    doc_index: OpenRpcDocumentIndex,
    current_source_path: str,
    param: JsonObject,
) -> OpenRpcParamDetail:
    schema = param.get("schema")
    return {
        "name": str(param.get("name") or ""),
        "description": str(param.get("description") or ""),
        "schema_name": ref_schema_name(schema),
        "schema": schema_brief(doc_index, current_source_path, schema) if schema is not None else "-",
        "required_fields": schema_required_field_names(doc_index, current_source_path, schema) if schema is not None else [],
        "sample": schema_sample_value(doc_index, current_source_path, schema) if schema is not None else None,
    }


def extract_result_detail(
    doc_index: OpenRpcDocumentIndex,
    current_source_path: str,
    result: JsonValue | None,
) -> OpenRpcResultDetail:
    if not isinstance(result, dict):
        return {
            "name": "",
            "description": "",
            "schema_name": None,
            "schema": "-",
            "required_fields": [],
            "sample": None,
        }
    schema = result.get("schema")
    return {
        "name": str(result.get("name") or ""),
        "description": str(result.get("description") or ""),
        "schema_name": ref_schema_name(schema),
        "schema": schema_brief(doc_index, current_source_path, schema) if schema is not None else "-",
        "required_fields": schema_required_field_names(doc_index, current_source_path, schema) if schema is not None else [],
        "sample": schema_sample_value(doc_index, current_source_path, schema) if schema is not None else None,
    }


def extract_method_detail(
    document: OpenRpcDocument,
    *,
    doc_index: OpenRpcDocumentIndex,
    current_source_path: str,
) -> OpenRpcMethodDetailsByName:
    methods = document.get("methods")
    if not isinstance(methods, list):
        return {}

    details: OpenRpcMethodDetailsByName = {}
    for method in methods:
        if not isinstance(method, dict):
            continue
        name = method.get("name")
        if not isinstance(name, str) or not name:
            continue
        params = method.get("params")
        if not isinstance(params, list):
            params = []
        detail: OpenRpcMethodDetail = {
            "name": name,
            "anchor": method_anchor(name),
            "summary": str(method.get("summary") or ""),
            "description": str(method.get("description") or ""),
            "lifecycle_state": normalize_lifecycle_state(method.get("x-state")),
            "replaces": str(method.get("x-replaces")) if isinstance(method.get("x-replaces"), str) else None,
            "params": [extract_param_detail(doc_index, current_source_path, param) for param in params if isinstance(param, dict)],
            "result": extract_result_detail(doc_index, current_source_path, method.get("result")),
            "fingerprint": "",
        }
        detail["fingerprint"] = sha256_json(
            {
                "summary": detail["summary"],
                "description": detail["description"],
                "lifecycle_state": detail["lifecycle_state"],
                "replaces": detail["replaces"],
                "params": detail["params"],
                "result": detail["result"],
            }
        )
        details[name] = detail
    return details


def render_name_list(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names)


def describe_param_changes(previous: OpenRpcValueDetail, current: OpenRpcValueDetail) -> list[str]:
    changes: list[str] = []
    if previous["description"] != current["description"]:
        changes.append("description")
    if previous["schema"] != current["schema"]:
        changes.append("schema")
    if previous["schema_name"] != current["schema_name"]:
        changes.append("schema ref")
    if previous["required_fields"] != current["required_fields"]:
        changes.append("required fields")
    return changes


def describe_method_changes(previous: OpenRpcMethodDetail, current: OpenRpcMethodDetail) -> list[str]:
    changes: list[str] = []
    if previous["summary"] != current["summary"]:
        changes.append("summary updated")
    if previous["description"] != current["description"]:
        changes.append("description updated")
    if previous.get("lifecycle_state") != current.get("lifecycle_state"):
        changes.append("lifecycle state updated")
    if previous.get("replaces") != current.get("replaces"):
        changes.append("replacement target updated")

    previous_params = {param["name"]: param for param in previous["params"]}
    current_params = {param["name"]: param for param in current["params"]}
    added = sorted(name for name in current_params if name not in previous_params)
    removed = sorted(name for name in previous_params if name not in current_params)
    updated = sorted(
        name
        for name in previous_params.keys() & current_params.keys()
        if describe_param_changes(previous_params[name], current_params[name])
    )
    if added:
        changes.append(f"params added: {render_name_list(added)}")
    if removed:
        changes.append(f"params removed: {render_name_list(removed)}")
    if updated:
        changes.append(f"params updated: {render_name_list(updated)}")

    previous_result = previous["result"]
    current_result = current["result"]
    result_changes: list[str] = []
    if previous_result["description"] != current_result["description"]:
        result_changes.append("description")
    if previous_result["schema"] != current_result["schema"]:
        result_changes.append("schema")
    if previous_result["schema_name"] != current_result["schema_name"]:
        result_changes.append("schema ref")
    if previous_result["required_fields"] != current_result["required_fields"]:
        result_changes.append("required fields")
    if result_changes:
        changes.append(f"result updated ({', '.join(result_changes)})")
    return changes


def build_openrpc_report_from_sources(
    sources: list[OpenRpcSourceSnapshot],
    *,
    source_name: str,
    version_filter: str,
    publish_version: str | None = None,
) -> OpenRpcReport:
    if not sources:
        raise ValueError("At least one OpenRPC snapshot is required")

    ordered_versions = sorted({snapshot.version for snapshot in sources}, key=version_key)
    selected_publish_version = publish_version or ordered_versions[-1]
    if selected_publish_version not in ordered_versions:
        raise ValueError(
            f"Publish version '{selected_publish_version}' is not present in selected snapshots: {ordered_versions}"
        )

    scoped_versions = ordered_versions[: ordered_versions.index(selected_publish_version) + 1]
    scoped_sources = [snapshot for snapshot in sources if snapshot.version in scoped_versions]
    version_doc_index = build_version_doc_index(scoped_sources)

    snapshots_by_spec: dict[str, list[OpenRpcSourceSnapshot]] = {}
    for snapshot in scoped_sources:
        snapshots_by_spec.setdefault(snapshot.spec_id, []).append(snapshot)

    specs: list[OpenRpcSpecLifecycle] = []
    for spec_id, spec_snapshots in sorted(snapshots_by_spec.items()):
        spec_snapshots.sort(key=lambda snapshot: version_key(snapshot.version))
        versions_present = [snapshot.version for snapshot in spec_snapshots]
        display_name = spec_snapshots[-1].display_name

        per_version_methods: dict[str, OpenRpcMethodDetailsByName] = {}
        for snapshot in spec_snapshots:
            per_version_methods[snapshot.version] = extract_method_detail(
                snapshot.document,
                doc_index=version_doc_index[snapshot.version],
                current_source_path=snapshot.source_path,
            )

        method_history: dict[str, OpenRpcMethodHistory] = {}
        for snapshot in spec_snapshots:
            current_methods = per_version_methods[snapshot.version]
            for method_name, method_detail in current_methods.items():
                history = method_history.setdefault(
                    method_name,
                    {
                        "versions": [],
                        "details": {},
                        "fingerprints": {},
                        "changed_in": [],
                        "change_details": [],
                    },
                )
                history["versions"].append(snapshot.version)
                history["details"][snapshot.version] = method_detail
                previous_version = history["versions"][-2] if len(history["versions"]) > 1 else None
                if previous_version is not None and history["fingerprints"].get(previous_version) != method_detail["fingerprint"]:
                    changes = describe_method_changes(history["details"][previous_version], method_detail)
                    history["changed_in"].append(snapshot.version)
                    history["change_details"].append(
                        {
                            "version": snapshot.version,
                            "changes": changes or ["details updated"],
                        }
                    )
                history["fingerprints"][snapshot.version] = method_detail["fingerprint"]

        per_version_deltas: dict[str, dict[str, int]] = {}
        for index, version in enumerate(scoped_versions):
            current_methods = per_version_methods.get(version, {})
            if index == 0:
                per_version_deltas[version] = {
                    "active_count": len(current_methods),
                    "added_count": 0,
                    "changed_count": 0,
                    "removed_count": 0,
                }
                continue
            previous_version = scoped_versions[index - 1]
            previous_methods = per_version_methods.get(previous_version, {})
            added = len(set(current_methods) - set(previous_methods))
            removed = len(set(previous_methods) - set(current_methods))
            changed = sum(1 for history in method_history.values() if version in history["changed_in"])
            per_version_deltas[version] = {
                "active_count": len(current_methods),
                "added_count": added,
                "changed_count": changed,
                "removed_count": removed,
            }

        publish_methods = per_version_methods.get(selected_publish_version, {})
        merged_methods: list[OpenRpcMethodLifecycle] = []
        publish_names = set(publish_methods)
        for method_name, method_detail in publish_methods.items():
            history = method_history[method_name]
            merged_methods.append(
                OpenRpcMethodLifecycle(
                    method=method_name,
                    anchor=method_detail["anchor"],
                    introduced_version=history["versions"][0],
                    changed_in_versions=list(history["changed_in"]),
                    change_details=list(history["change_details"]),
                    removed_version=None,
                    last_seen_in=history["versions"][-1],
                    status="active",
                    lifecycle_state=method_detail.get("lifecycle_state"),
                    replaces=method_detail.get("replaces"),
                    latest=method_detail,
                )
            )

        for method_name, history in method_history.items():
            if method_name in publish_names:
                continue
            last_seen_in = history["versions"][-1]
            removed_in = None
            last_seen_index = scoped_versions.index(last_seen_in)
            for candidate in scoped_versions[last_seen_index + 1 :]:
                if candidate not in history["versions"]:
                    removed_in = candidate
                    break
            merged_methods.append(
                OpenRpcMethodLifecycle(
                    method=method_name,
                    anchor=history["details"][last_seen_in]["anchor"],
                    introduced_version=history["versions"][0],
                    changed_in_versions=list(history["changed_in"]),
                    change_details=list(history["change_details"]),
                    removed_version=removed_in,
                    last_seen_in=last_seen_in,
                    status="removed",
                    lifecycle_state=history["details"][last_seen_in].get("lifecycle_state"),
                    replaces=history["details"][last_seen_in].get("replaces"),
                    latest=history["details"][last_seen_in],
                )
            )

        merged_methods.sort(key=lambda method: (1 if method.status == "removed" else 0, method.method))

        latest_snapshot = spec_snapshots[-1]
        info = latest_snapshot.document.get("info")
        if not isinstance(info, dict):
            info = {}

        spec_changed_in_versions = sorted(
            {
                version
                for method in merged_methods
                for version in method.changed_in_versions
            },
            key=version_key,
        )

        specs.append(
            OpenRpcSpecLifecycle(
                spec_id=spec_id,
                display_name=display_name,
                latest_source_path=latest_snapshot.source_path,
                introduced_version=versions_present[0],
                changed_in_versions=spec_changed_in_versions,
                removed_version=None,
                versions_present=versions_present,
                latest_version=latest_snapshot.version,
                openrpc_version=str(latest_snapshot.document.get("openrpc")) if latest_snapshot.document.get("openrpc") else None,
                info_title=str(info.get("title")) if info.get("title") else None,
                info_version=str(info.get("version")) if info.get("version") else None,
                info_description=str(info.get("description")) if info.get("description") else None,
                per_version_method_deltas=per_version_deltas,
                methods=merged_methods,
            )
        )

    return OpenRpcReport(
        source_name=source_name,
        version_filter=version_filter,
        versions=scoped_versions,
        publish_version=selected_publish_version,
        specs=specs,
    )
