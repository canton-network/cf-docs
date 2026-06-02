"""Build lifecycle metadata for AsyncAPI specs across supplied snapshots."""

from __future__ import annotations

import hashlib
import json
import re

import yaml

from x2mdx.asyncapi.models import (
    AsyncApiActionDetail,
    AsyncApiChannelDetail,
    AsyncApiChannelHistory,
    AsyncApiDocument,
    AsyncApiChannelLifecycle,
    AsyncApiMessageDetail,
    AsyncApiReport,
    AsyncApiSourceSnapshot,
)
from x2mdx.types import JsonValue, require_json_object, require_json_value

REQUEST_SAMPLE_MAX_DEPTH = 4
REQUEST_SAMPLE_MAX_PROPERTIES = 8
AsyncApiChannelsByName = dict[str, AsyncApiChannelDetail]


def sha256_json(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def version_key(version: str) -> tuple[tuple[int, int | str], ...]:
    version_text = version[1:] if version.startswith("v") else version
    parts = re.split(r"[.\-+]", version_text)
    key: list[tuple[int, int | str]] = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return tuple(key)


def parse_asyncapi(raw_text: str) -> AsyncApiDocument:
    obj = require_json_object(yaml.safe_load(raw_text))
    version = obj.get("asyncapi")
    if not isinstance(version, str) or not version:
        raise ValueError("Document does not contain top-level `asyncapi` key")

    document: AsyncApiDocument = {"asyncapi": version}
    info = obj.get("info")
    if info is not None:
        if not isinstance(info, dict):
            raise ValueError("AsyncAPI document `info` must be an object")
        document["info"] = info
    channels = obj.get("channels")
    if channels is not None:
        if not isinstance(channels, dict):
            raise ValueError("AsyncAPI document `channels` must be an object")
        document["channels"] = channels
    components = obj.get("components")
    if components is not None:
        if not isinstance(components, dict):
            raise ValueError("AsyncAPI document `components` must be an object")
        document["components"] = components
    return document


def slugify(value: str) -> str:
    output = value.lower()
    output = re.sub(r"[^a-z0-9]+", "-", output)
    output = re.sub(r"-{2,}", "-", output).strip("-")
    return output


def channel_anchor(channel: str) -> str:
    return f"channel-{slugify(channel)}"


def normalize_lifecycle_state(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"alpha", "beta", "stable", "deprecated"}:
        return normalized
    return None


def resolve_local_ref(doc: AsyncApiDocument, node: JsonValue | None, max_depth: int = 8) -> JsonValue | None:
    current = node
    depth = 0
    while isinstance(current, dict) and "$ref" in current and depth < max_depth:
        ref = current["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            break
        target = require_json_value(doc)
        valid = True
        for part in ref[2:].split("/"):
            if isinstance(target, dict) and part in target:
                target = target[part]
            else:
                valid = False
                break
        if not valid:
            break
        current = target
        depth += 1
    return current


def local_ref_name(node: JsonValue | None, *, prefix: str) -> str | None:
    if not isinstance(node, dict):
        return None
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return None
    marker = f"#/{prefix}/"
    if not ref.startswith(marker):
        return None
    return ref[len(marker) :]


def object_schema_properties_and_required(
    doc: AsyncApiDocument,
    schema: JsonValue | None,
    *,
    max_depth: int = 6,
) -> tuple[dict[str, JsonValue], set[str]]:
    if max_depth <= 0:
        return {}, set()

    resolved = resolve_local_ref(doc, schema)
    if not isinstance(resolved, dict):
        return {}, set()

    properties: dict[str, JsonValue] = {}
    required: set[str] = set()

    all_of = resolved.get("allOf")
    if isinstance(all_of, list):
        for item in all_of:
            item_properties, item_required = object_schema_properties_and_required(
                doc,
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


def schema_required_field_names(doc: AsyncApiDocument, schema: JsonValue | None) -> list[str]:
    properties, required = object_schema_properties_and_required(doc, schema)
    if not required:
        return []

    known = sorted(name for name in required if name in properties)
    unknown = sorted(name for name in required if name not in properties)
    return [*known, *unknown]


def schema_brief(doc: AsyncApiDocument, schema: JsonValue | None) -> str:
    resolved = resolve_local_ref(doc, schema)
    if not isinstance(resolved, dict):
        return "-"

    type_name = resolved.get("type")
    if isinstance(type_name, str):
        if type_name == "array":
            return f"array[{schema_brief(doc, resolved.get('items'))}]"
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


def schema_type_token(doc: AsyncApiDocument, schema: JsonValue | None) -> JsonValue:
    resolved = resolve_local_ref(doc, schema)
    if not isinstance(resolved, dict):
        return "<value>"

    one_of = resolved.get("oneOf")
    if isinstance(one_of, list) and one_of:
        return schema_type_token(doc, one_of[0])

    any_of = resolved.get("anyOf")
    if isinstance(any_of, list) and any_of:
        return schema_type_token(doc, any_of[0])

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
        return [schema_type_token(doc, resolved.get("items"))]

    properties, _required = object_schema_properties_and_required(doc, resolved)
    if type_name == "object" or properties or isinstance(resolved.get("allOf"), list):
        return "<object>"

    return "<value>"


def schema_sample_value(
    doc: AsyncApiDocument,
    schema: JsonValue | None,
    *,
    max_depth: int = REQUEST_SAMPLE_MAX_DEPTH,
    max_properties: int = REQUEST_SAMPLE_MAX_PROPERTIES,
    required_only: bool = True,
    seen_refs: set[str] | None = None,
) -> JsonValue:
    if max_depth <= 0:
        return schema_type_token(doc, schema)

    if seen_refs is None:
        seen_refs = set()

    if isinstance(schema, dict):
        ref = schema.get("$ref")
        if isinstance(ref, str):
            if ref in seen_refs:
                return schema_type_token(doc, schema)
            return schema_sample_value(
                doc,
                resolve_local_ref(doc, schema),
                max_depth=max_depth,
                max_properties=max_properties,
                required_only=required_only,
                seen_refs=seen_refs | {ref},
            )

    resolved = resolve_local_ref(doc, schema)
    if not isinstance(resolved, dict):
        return schema_type_token(doc, schema)

    one_of = resolved.get("oneOf")
    if isinstance(one_of, list) and one_of:
        return schema_sample_value(
            doc,
            one_of[0],
            max_depth=max_depth,
            max_properties=max_properties,
            required_only=required_only,
            seen_refs=seen_refs,
        )

    any_of = resolved.get("anyOf")
    if isinstance(any_of, list) and any_of:
        return schema_sample_value(
            doc,
            any_of[0],
            max_depth=max_depth,
            max_properties=max_properties,
            required_only=required_only,
            seen_refs=seen_refs,
        )

    properties, required = object_schema_properties_and_required(doc, resolved, max_depth=max_depth)
    type_name = resolved.get("type")
    if type_name == "object" or properties or isinstance(resolved.get("allOf"), list):
        property_names = list(properties.keys())
        required_names = [name for name in property_names if name in required]
        unknown_required_names = sorted(name for name in required if name not in properties)
        names_to_render = required_names if required_only and required_names else property_names
        if not names_to_render and unknown_required_names:
            names_to_render = unknown_required_names

        sample: dict[str, JsonValue] = {}
        for name in names_to_render[:max_properties]:
            if name in properties:
                sample[name] = schema_sample_value(
                    doc,
                    properties[name],
                    max_depth=max_depth - 1,
                    max_properties=max_properties,
                    required_only=required_only,
                    seen_refs=seen_refs,
                )
            else:
                sample[name] = "<value>"
        return sample

    if type_name == "array":
        return [
            schema_sample_value(
                doc,
                resolved.get("items"),
                max_depth=max_depth - 1,
                max_properties=max_properties,
                required_only=required_only,
                seen_refs=seen_refs,
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

    return schema_type_token(doc, resolved)


def extract_message_detail(doc: AsyncApiDocument, message_node: JsonValue | None) -> AsyncApiMessageDetail:
    resolved_message = resolve_local_ref(doc, message_node)
    message_name = local_ref_name(message_node, prefix="components/messages")
    if not isinstance(resolved_message, dict):
        return {
            "name": message_name or "-",
            "content_type": "-",
            "payload_schema": "-",
            "required_fields": [],
            "sample": None,
        }

    payload = resolved_message.get("payload")
    return {
        "name": message_name or str(resolved_message.get("name") or resolved_message.get("title") or "-"),
        "content_type": str(resolved_message.get("contentType") or "-"),
        "payload_schema": schema_brief(doc, payload) if payload is not None else "-",
        "required_fields": schema_required_field_names(doc, payload) if payload is not None else [],
        "sample": schema_sample_value(doc, payload) if payload is not None else None,
    }


def extract_action_detail(doc: AsyncApiDocument, action_name: str, action_node: JsonValue | None) -> AsyncApiActionDetail:
    resolved_action = resolve_local_ref(doc, action_node)
    if not isinstance(resolved_action, dict):
        return {
            "action": action_name,
            "operation_id": "",
            "description": "",
            "ws_method": "",
            "message": extract_message_detail(doc, None),
        }

    bindings = resolved_action.get("bindings")
    ws_method = ""
    if isinstance(bindings, dict):
        ws = bindings.get("ws")
        if isinstance(ws, dict):
            ws_method = str(ws.get("method") or "")

    return {
        "action": action_name,
        "operation_id": str(resolved_action.get("operationId") or ""),
        "description": str(resolved_action.get("description") or ""),
        "ws_method": ws_method,
        "message": extract_message_detail(doc, resolved_action.get("message")),
    }


def extract_channel_detail(doc: AsyncApiDocument, channel_name: str, channel_node: JsonValue | None) -> AsyncApiChannelDetail:
    resolved_channel = resolve_local_ref(doc, channel_node)
    if not isinstance(resolved_channel, dict):
        resolved_channel = {}

    actions: list[AsyncApiActionDetail] = []
    for action_name in ("publish", "subscribe"):
        if action_name in resolved_channel:
            actions.append(extract_action_detail(doc, action_name, resolved_channel[action_name]))

    return {
        "channel": channel_name,
        "anchor": channel_anchor(channel_name),
        "description": str(resolved_channel.get("description") or ""),
        "lifecycle_state": normalize_lifecycle_state(resolved_channel.get("x-state")),
        "replaces": str(resolved_channel.get("x-replaces")) if isinstance(resolved_channel.get("x-replaces"), str) else None,
        "actions": actions,
        "action_names": [action["action"] for action in actions],
    }


def render_name_list(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names)


def describe_action_changes(
    previous: AsyncApiActionDetail | None,
    current: AsyncApiActionDetail | None,
    *,
    action_name: str,
) -> list[str]:
    if previous is None and current is None:
        return []
    label = action_name
    if previous is None:
        return [f"{label} action added"]
    if current is None:
        return [f"{label} action removed"]

    changes: list[str] = []
    if previous["operation_id"] != current["operation_id"]:
        changes.append(f"{label} operation id changed")
    if previous["description"] != current["description"]:
        changes.append(f"{label} description updated")
    if previous["ws_method"] != current["ws_method"]:
        changes.append(
            f"{label} websocket method changed `{previous['ws_method'] or '-'}` -> `{current['ws_method'] or '-'}`"
        )

    previous_message = previous["message"]
    current_message = current["message"]
    if previous_message["name"] != current_message["name"]:
        changes.append(
            f"{label} message changed `{previous_message['name'] or '-'}` -> `{current_message['name'] or '-'}`"
        )
    if previous_message["content_type"] != current_message["content_type"]:
        changes.append(
            f"{label} content type changed `{previous_message['content_type']}` -> `{current_message['content_type']}`"
        )
    if previous_message["payload_schema"] != current_message["payload_schema"]:
        changes.append(
            f"{label} payload schema changed `{previous_message['payload_schema']}` -> `{current_message['payload_schema']}`"
        )

    previous_required = set(previous_message["required_fields"])
    current_required = set(current_message["required_fields"])
    added_required = sorted(current_required - previous_required)
    removed_required = sorted(previous_required - current_required)
    if added_required:
        changes.append(f"{label} required fields added: {render_name_list(added_required)}")
    if removed_required:
        changes.append(f"{label} required fields removed: {render_name_list(removed_required)}")
    return changes


def describe_channel_changes(previous: AsyncApiChannelDetail, current: AsyncApiChannelDetail) -> list[str]:
    changes: list[str] = []
    if previous["description"] != current["description"]:
        changes.append("channel description updated")
    if previous.get("lifecycle_state") != current.get("lifecycle_state"):
        changes.append("channel lifecycle state updated")
    if previous.get("replaces") != current.get("replaces"):
        changes.append("channel replacement target updated")

    previous_actions = {action["action"]: action for action in previous["actions"]}
    current_actions = {action["action"]: action for action in current["actions"]}
    for action_name in ("publish", "subscribe"):
        changes.extend(
            describe_action_changes(
                previous_actions.get(action_name),
                current_actions.get(action_name),
                action_name=action_name,
            )
        )
    return changes


def collect_snapshot_channels(document: AsyncApiDocument) -> AsyncApiChannelsByName:
    channels = document.get("channels")
    if not isinstance(channels, dict):
        return {}

    details: AsyncApiChannelsByName = {}
    for channel_name in sorted(channels):
        details[channel_name] = extract_channel_detail(document, channel_name, channels[channel_name])
    return details


def build_asyncapi_report_from_sources(
    sources: list[AsyncApiSourceSnapshot],
    *,
    source_name: str,
    version_filter: str,
    publish_version: str | None = None,
) -> AsyncApiReport:
    if not sources:
        raise ValueError("At least one AsyncAPI snapshot is required")

    ordered_sources = sorted(sources, key=lambda snapshot: version_key(snapshot.version))
    ordered_versions = [snapshot.version for snapshot in ordered_sources]
    selected_publish_version = publish_version or ordered_versions[-1]
    if selected_publish_version not in ordered_versions:
        raise ValueError(
            f"Publish version '{selected_publish_version}' is not present in selected snapshots: {ordered_versions}"
        )

    publish_index = ordered_versions.index(selected_publish_version)
    scoped_sources = ordered_sources[: publish_index + 1]

    snapshot_channels: dict[str, AsyncApiChannelsByName] = {}
    for snapshot in scoped_sources:
        snapshot_channels[snapshot.version] = collect_snapshot_channels(snapshot.document)

    channel_history: dict[str, AsyncApiChannelHistory] = {}
    for snapshot in scoped_sources:
        current_channels = snapshot_channels[snapshot.version]
        for channel_name, channel_detail in current_channels.items():
            fingerprint = sha256_json(channel_detail)
            history = channel_history.setdefault(
                channel_name,
                {
                    "versions": [],
                    "details": {},
                    "fingerprints": {},
                    "changed_in": [],
                    "change_details": [],
                },
            )
            history["versions"].append(snapshot.version)
            history["details"][snapshot.version] = channel_detail
            previous_version = history["versions"][-2] if len(history["versions"]) > 1 else None
            if previous_version is not None and history["fingerprints"].get(previous_version) != fingerprint:
                changes = describe_channel_changes(history["details"][previous_version], channel_detail)
                history["changed_in"].append(snapshot.version)
                history["change_details"].append(
                    {
                        "version": snapshot.version,
                        "changes": changes or ["details updated"],
                    }
                )
            history["fingerprints"][snapshot.version] = fingerprint

    per_version_deltas: dict[str, dict[str, int]] = {}
    for index, version in enumerate(snapshot.version for snapshot in scoped_sources):
        if index == 0:
            per_version_deltas[version] = {"active_count": len(snapshot_channels[version]), "added_count": 0, "changed_count": 0, "removed_count": 0}
            continue
        added_count = 0
        changed_count = 0
        removed_count = 0
        for history in channel_history.values():
            if history["versions"][0] == version:
                added_count += 1
            if version in history["changed_in"]:
                changed_count += 1
            if version not in history["versions"]:
                previous_version = scoped_sources[index - 1].version
                if previous_version in history["versions"]:
                    removed_count += 1
        per_version_deltas[version] = {
            "active_count": len(snapshot_channels[version]),
            "added_count": added_count,
            "changed_count": changed_count,
            "removed_count": removed_count,
        }

    publish_channels = snapshot_channels[selected_publish_version]
    merged_channels: list[AsyncApiChannelLifecycle] = []
    publish_names = set(publish_channels)

    for channel_name, channel_detail in publish_channels.items():
        history = channel_history[channel_name]
        merged_channels.append(
            AsyncApiChannelLifecycle(
                channel=channel_name,
                anchor=channel_detail["anchor"],
                introduced_version=history["versions"][0],
                changed_in_versions=list(history["changed_in"]),
                change_details=list(history["change_details"]),
                removed_version=None,
                last_seen_in=history["versions"][-1],
                status="active",
                lifecycle_state=channel_detail.get("lifecycle_state"),
                replaces=channel_detail.get("replaces"),
                latest=channel_detail,
            )
        )

    for channel_name, history in channel_history.items():
        if channel_name in publish_names:
            continue
        last_seen_in = history["versions"][-1]
        last_seen_index = ordered_versions.index(last_seen_in)
        removed_in = None
        for candidate in ordered_versions[last_seen_index + 1 : publish_index + 1]:
            if candidate not in history["versions"]:
                removed_in = candidate
                break
        merged_channels.append(
            AsyncApiChannelLifecycle(
                channel=channel_name,
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

    merged_channels.sort(key=lambda channel: (1 if channel.status == "removed" else 0, channel.channel))

    latest_snapshot = scoped_sources[-1]
    info = latest_snapshot.document.get("info")
    if not isinstance(info, dict):
        info = {}

    return AsyncApiReport(
        source_name=source_name,
        version_filter=version_filter,
        versions=[snapshot.version for snapshot in scoped_sources],
        publish_version=selected_publish_version,
        asyncapi_version=str(latest_snapshot.document.get("asyncapi")) if latest_snapshot.document.get("asyncapi") else None,
        info_title=str(info.get("title")) if info.get("title") else None,
        info_description=str(info.get("description")) if info.get("description") else None,
        latest_source_path=latest_snapshot.source_path,
        per_version_deltas=per_version_deltas,
        channels=merged_channels,
    )
