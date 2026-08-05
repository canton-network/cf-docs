from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
HISTORY_MARKER = "**Endpoint history**:"


@dataclass(frozen=True)
class OperationChange:
    version: str
    changes: list[str]


@dataclass(frozen=True)
class OperationHistory:
    method: str
    path: str
    added_version: str
    changed_versions: list[OperationChange]
    removed_version: str | None
    deprecated: bool


def operation_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def operation_items(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return {}

    operations: dict[str, dict[str, Any]] = {}
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            method_name = str(method).lower()
            if method_name not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operations[operation_key(method_name, path)] = operation
    return operations


def resolved_local_ref(spec: dict[str, Any], ref: str) -> Any:
    if not ref.startswith("#/"):
        return None
    current: Any = spec
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def collect_local_refs(value: Any, refs: set[str]) -> None:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            refs.add(ref)
        for item in value.values():
            collect_local_refs(item, refs)
    elif isinstance(value, list):
        for item in value:
            collect_local_refs(item, refs)


def referenced_values(spec: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    seen: set[str] = set()
    pending: set[str] = set()
    collect_local_refs(operation, pending)
    values: dict[str, Any] = {}

    while pending:
        ref = pending.pop()
        if ref in seen:
            continue
        seen.add(ref)
        resolved = resolved_local_ref(spec, ref)
        if resolved is None:
            continue
        values[ref] = strip_generated_history(copy.deepcopy(resolved))
        collect_local_refs(resolved, pending)
    return values


def strip_generated_history(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key == "x-mint" and isinstance(item, dict):
                mint = {
                    mint_key: strip_generated_history(mint_value)
                    for mint_key, mint_value in item.items()
                    if not (mint_key == "content" and isinstance(mint_value, str) and HISTORY_MARKER in mint_value)
                }
                if mint:
                    cleaned[key] = mint
                continue
            cleaned[key] = strip_generated_history(item)
        return cleaned
    if isinstance(value, list):
        return [strip_generated_history(item) for item in value]
    return value


def fingerprint_operation(spec: dict[str, Any], operation: dict[str, Any]) -> str:
    payload = {
        "operation": strip_generated_history(copy.deepcopy(operation)),
        "referenced": referenced_values(spec, operation),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def schema_ref_or_type(value: Any) -> str:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            return ref.rsplit("/", 1)[-1]
        schema_type = value.get("type")
        if isinstance(schema_type, str):
            if schema_type == "array":
                return f"array[{schema_ref_or_type(value.get('items'))}]"
            return schema_type
        for keyword in ("oneOf", "anyOf", "allOf"):
            if isinstance(value.get(keyword), list):
                return keyword
    return "-"


def schema_signature(spec: dict[str, Any] | None, value: Any) -> str:
    label = schema_ref_or_type(value)
    resolved = value
    if spec is not None and isinstance(value, dict) and isinstance(value.get("$ref"), str):
        resolved = resolved_local_ref(spec, value["$ref"])
    if resolved is None:
        return label
    encoded = json.dumps(strip_generated_history(copy.deepcopy(resolved)), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{label}:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


def response_schemas(operation: dict[str, Any], spec: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return {}

    output: dict[str, dict[str, str]] = {}
    for code, response in responses.items():
        if not isinstance(response, dict):
            continue
        content = response.get("content")
        if not isinstance(content, dict):
            output[str(code)] = {}
            continue
        output[str(code)] = {
            str(content_type): schema_signature(spec, media_type.get("schema") if isinstance(media_type, dict) else None)
            for content_type, media_type in content.items()
        }
    return output


def request_body_schemas(operation: dict[str, Any], spec: dict[str, Any] | None = None) -> dict[str, str]:
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return {}
    content = request_body.get("content")
    if not isinstance(content, dict):
        return {}
    return {
        str(content_type): schema_signature(spec, media_type.get("schema") if isinstance(media_type, dict) else None)
        for content_type, media_type in content.items()
    }


def parameter_map(operation: dict[str, Any]) -> dict[tuple[str, str], str]:
    parameters = operation.get("parameters")
    if not isinstance(parameters, list):
        return {}
    output: dict[tuple[str, str], str] = {}
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        name = parameter.get("name")
        location = parameter.get("in")
        if not isinstance(name, str) or not isinstance(location, str):
            continue
        required = "required" if bool(parameter.get("required")) else "optional"
        output[(location, name)] = f"{required}:{schema_ref_or_type(parameter.get('schema'))}"
    return output


def summarize_operation_changes(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    previous_spec: dict[str, Any] | None = None,
    current_spec: dict[str, Any] | None = None,
) -> list[str]:
    changes: list[str] = []
    if (previous.get("operationId") or "") != (current.get("operationId") or ""):
        changes.append("operation id changed")
    if (previous.get("summary") or "") != (current.get("summary") or ""):
        changes.append("summary updated")
    if (previous.get("description") or "") != (current.get("description") or ""):
        changes.append("description updated")
    if bool(previous.get("deprecated")) != bool(current.get("deprecated")):
        changes.append("deprecation flag changed")
    if (previous.get("x-state") or "") != (current.get("x-state") or ""):
        changes.append("lifecycle state changed")
    if (previous.get("x-replaces") or "") != (current.get("x-replaces") or ""):
        changes.append("replacement target changed")

    previous_parameters = parameter_map(previous)
    current_parameters = parameter_map(current)
    for key in sorted(current_parameters.keys() - previous_parameters.keys()):
        changes.append(f"{key[0]} parameter `{key[1]}` added")
    for key in sorted(previous_parameters.keys() - current_parameters.keys()):
        changes.append(f"{key[0]} parameter `{key[1]}` removed")
    for key in sorted(previous_parameters.keys() & current_parameters.keys()):
        if previous_parameters[key] != current_parameters[key]:
            changes.append(f"{key[0]} parameter `{key[1]}` changed")

    previous_request = request_body_schemas(previous, previous_spec)
    current_request = request_body_schemas(current, current_spec)
    if not previous_request and current_request:
        changes.append("request body added")
    elif previous_request and not current_request:
        changes.append("request body removed")
    elif previous_request != current_request:
        changes.append("request body schema changed")

    previous_responses = response_schemas(previous, previous_spec)
    current_responses = response_schemas(current, current_spec)
    for code in sorted(current_responses.keys() - previous_responses.keys()):
        changes.append(f"response `{code}` added")
    for code in sorted(previous_responses.keys() - current_responses.keys()):
        changes.append(f"response `{code}` removed")
    for code in sorted(previous_responses.keys() & current_responses.keys()):
        previous_response = previous.get("responses", {}).get(code, {}) if isinstance(previous.get("responses"), dict) else {}
        current_response = current.get("responses", {}).get(code, {}) if isinstance(current.get("responses"), dict) else {}
        if isinstance(previous_response, dict) and isinstance(current_response, dict):
            if (previous_response.get("description") or "") != (current_response.get("description") or ""):
                changes.append(f"response `{code}` description updated")
        if previous_responses[code] != current_responses[code]:
            changes.append(f"response `{code}` schema changed")

    return changes or ["operation schema changed"]


def build_operation_histories(specs_by_version: dict[str, dict[str, Any]], versions: list[str]) -> dict[str, OperationHistory]:
    operations_by_version = {version: operation_items(specs_by_version[version]) for version in versions}
    all_keys = sorted({key for operations in operations_by_version.values() for key in operations})
    histories: dict[str, OperationHistory] = {}

    for key in all_keys:
        present_versions = [version for version in versions if key in operations_by_version[version]]
        if not present_versions:
            continue

        changed_versions: list[OperationChange] = []
        previous_version: str | None = None
        previous_hash: str | None = None
        for version in present_versions:
            operation = operations_by_version[version][key]
            current_hash = fingerprint_operation(specs_by_version[version], operation)
            if previous_hash is not None and current_hash != previous_hash and previous_version is not None:
                changed_versions.append(
                    OperationChange(
                        version=version,
                        changes=summarize_operation_changes(
                            operations_by_version[previous_version][key],
                            operation,
                            previous_spec=specs_by_version[previous_version],
                            current_spec=specs_by_version[version],
                        ),
                    )
                )
            previous_hash = current_hash
            previous_version = version

        method, path = key.split(" ", 1)
        latest_operation = operations_by_version[present_versions[-1]][key]
        latest_index = versions.index(present_versions[-1])
        removed_version = versions[latest_index + 1] if latest_index + 1 < len(versions) else None
        histories[key] = OperationHistory(
            method=method,
            path=path,
            added_version=present_versions[0],
            changed_versions=changed_versions,
            removed_version=removed_version,
            deprecated=bool(latest_operation.get("deprecated")),
        )

    return histories


def compact_changes(changes: list[str], *, limit: int = 4) -> str:
    if len(changes) <= limit:
        return "; ".join(changes)
    shown = "; ".join(changes[:limit])
    return f"{shown}; +{len(changes) - limit} more"


def history_note(history: OperationHistory, first_version: str) -> str | None:
    parts: list[str] = []
    if history.added_version != first_version or history.changed_versions or history.deprecated:
        parts.append(f"Added in {history.added_version}.")
    for change in history.changed_versions:
        parts.append(f"Modified in {change.version}: {compact_changes(change.changes)}.")
    if history.deprecated:
        parts.append("Currently deprecated.")
    if history.removed_version is not None:
        parts.append(f"Removed in {history.removed_version}.")
    if not parts:
        return None
    return " ".join(parts)


def strip_generated_x_mint_content(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.fullmatch(r"(?P<indent>\s*)x-mint:\s*", line)
        if match is None:
            output.append(line)
            index += 1
            continue

        indent = match.group("indent")
        block = [line]
        index += 1
        while index < len(lines):
            candidate = lines[index]
            if candidate.strip() and not candidate.startswith(f"{indent} "):
                break
            block.append(candidate)
            index += 1

        if any(HISTORY_MARKER in block_line for block_line in block):
            continue
        output.extend(block)
    return "\n".join(output).rstrip() + "\n"


def render_history_x_mint_block(indent: str, note: str) -> list[str]:
    return [
        f"{indent}x-mint:",
        f"{indent}  content: |-",
        f"{indent}    <Note>",
        f"{indent}    {HISTORY_MARKER} {note}",
        f"{indent}    </Note>",
    ]


def enrich_openapi_text_with_history(
    text: str,
    histories: dict[str, OperationHistory],
    *,
    first_version: str,
) -> str:
    cleaned_text = strip_generated_x_mint_content(text)
    lines = cleaned_text.splitlines()
    output: list[str] = []
    in_paths = False
    paths_indent = ""
    current_path: str | None = None
    current_path_indent: str | None = None

    for line in lines:
        output.append(line)

        paths_match = re.fullmatch(r"(?P<indent>\s*)paths:\s*", line)
        if paths_match:
            in_paths = True
            paths_indent = paths_match.group("indent")
            current_path = None
            current_path_indent = None
            continue

        if not in_paths:
            continue

        if line and not line.startswith(f"{paths_indent} "):
            in_paths = False
            current_path = None
            current_path_indent = None
            continue

        path_match = re.fullmatch(rf"(?P<indent>{re.escape(paths_indent)}\s{{2}})(?P<path>/.*):\s*", line)
        if path_match:
            current_path = path_match.group("path")
            current_path_indent = path_match.group("indent")
            continue

        if current_path is None or current_path_indent is None:
            continue

        method_match = re.fullmatch(
            rf"(?P<indent>{re.escape(current_path_indent)}\s{{2}})(?P<method>{'|'.join(sorted(HTTP_METHODS))}):\s*",
            line,
        )
        if method_match is None:
            continue

        method = method_match.group("method").upper()
        history = histories.get(operation_key(method, current_path))
        if history is None or history.removed_version is not None:
            continue
        note = history_note(history, first_version)
        if note is None:
            continue
        output.extend(render_history_x_mint_block(f"{method_match.group('indent')}  ", note))

    return "\n".join(output).rstrip() + "\n"
