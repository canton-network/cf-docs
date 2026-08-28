from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from x2mdx.history.models import Evidence, EvidenceKind, HistoryEvent, HistoryEventKind
from x2mdx.reference_pages import (
    ReferenceBadge,
    ReferenceBreadcrumb,
    ReferenceExample,
    ReferenceField,
    ReferenceMetaItem,
    ReferenceOperationPage,
    ReferencePanel,
    ReferenceSchema,
    json_body,
    reference_badges_for_history_events,
    render_operation_page,
)


REMOVE_AS_OF_RE = re.compile(
    r"\b(?:will\s+be\s+)?removed\s+in\s+(?:the\s+)?(?:Canton\s+)?version\s+"
    r"(?P<version>v?\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?)",
    re.IGNORECASE,
)

LIFECYCLE_TITLE_RE = re.compile(
    r"^(?:deprecated|removed|obsolete)\b(?:$|\s*[:.\-]\s*|\s+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ManualOpenAPIRenderOptions:
    method: str
    path: str
    output_path: str
    server: str = "http://localhost:7575"
    surface_label: str = "JSON Ledger API"
    breadcrumbs: tuple[ReferenceBreadcrumb, ...] = ()
    auth_method: str | None = "bearer"
    authentication_label: str | None = "Bearer token"
    raw_spec_href: str | None = None
    playground: str = "interactive"


def _operation(spec: dict[str, Any], method: str, path: str) -> dict[str, Any]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI specification must define paths")
    path_item = paths.get(path)
    if not isinstance(path_item, dict):
        raise ValueError(f"OpenAPI path not found: {path}")
    operation = path_item.get(method.lower())
    if not isinstance(operation, dict):
        raise ValueError(f"OpenAPI operation not found: {method.upper()} {path}")
    return operation


def _path_item(spec: dict[str, Any], path: str) -> dict[str, Any]:
    paths = spec.get("paths")
    path_item = paths.get(path) if isinstance(paths, dict) else None
    return path_item if isinstance(path_item, dict) else {}


def _resolve_local_ref(spec: dict[str, Any], value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return value
    current: Any = spec
    for token in reference[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f"Unresolvable local OpenAPI reference: {reference}")
        current = current[token]
    return current


def _schema_name(schema: dict[str, Any], *, fallback: str) -> str:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        return reference.rsplit("/", 1)[-1]
    title = schema.get("title")
    return str(title).strip() if isinstance(title, str) and title.strip() else fallback


def _type_label(spec: dict[str, Any], schema: Any) -> str:
    if not isinstance(schema, dict):
        return "unknown"
    reference = schema.get("$ref")
    if isinstance(reference, str):
        return reference.rsplit("/", 1)[-1]
    if "oneOf" in schema:
        return "oneOf"
    if "anyOf" in schema:
        return "anyOf"
    schema_type = str(schema.get("type") or "object")
    if schema_type == "array":
        return f"{_type_label(spec, schema.get('items'))}[]"
    schema_format = schema.get("format")
    if isinstance(schema_format, str) and schema_format:
        return f"{schema_type} ({schema_format})"
    return schema_type


def _playground_type_label(spec: dict[str, Any], schema: Any) -> str:
    if not isinstance(schema, dict):
        return "object"
    if isinstance(schema.get("$ref"), str):
        return "object"
    if any(key in schema for key in ("oneOf", "anyOf", "allOf")):
        return "object"
    schema_type = str(schema.get("type") or "object")
    if schema_type == "array":
        item_type = _playground_type_label(spec, schema.get("items"))
        return f"{item_type}[]"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type in {"string", "boolean", "object"}:
        return schema_type
    return "object"


def _example_value(
    spec: dict[str, Any],
    schema: Any,
    *,
    depth: int = 0,
    seen_refs: frozenset[str] = frozenset(),
) -> Any:
    if not isinstance(schema, dict):
        return None
    for key in ("example", "default"):
        if key in schema:
            return schema[key]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]

    reference = schema.get("$ref")
    if isinstance(reference, str):
        if reference in seen_refs:
            return f"<{reference.rsplit('/', 1)[-1]}>"
        if depth >= 12:
            return "<object>"
        return _example_value(
            spec,
            _resolve_local_ref(spec, schema),
            depth=depth + 1,
            seen_refs=seen_refs | {reference},
        )
    for composition_key in ("oneOf", "anyOf", "allOf"):
        variants = schema.get(composition_key)
        if isinstance(variants, list) and variants:
            if composition_key == "allOf":
                merged: dict[str, Any] = {}
                for variant in variants:
                    value = _example_value(
                        spec,
                        variant,
                        depth=depth + 1,
                        seen_refs=seen_refs,
                    )
                    if isinstance(value, dict):
                        merged.update(value)
                return merged
            return _example_value(
                spec,
                variants[0],
                depth=depth + 1,
                seen_refs=seen_refs,
            )

    schema_type = schema.get("type")
    properties = schema.get("properties")
    if schema_type == "object" or isinstance(properties, dict):
        if depth >= 12:
            return "<object>"
        return {
            str(name): _example_value(
                spec,
                child,
                depth=depth + 1,
                seen_refs=seen_refs,
            )
            for name, child in (properties or {}).items()
        }
    if schema_type == "array":
        return [
            _example_value(
                spec,
                schema.get("items"),
                depth=depth + 1,
                seen_refs=seen_refs,
            )
        ]
    if schema_type == "integer":
        return 123
    if schema_type == "number":
        return 123.0
    if schema_type == "boolean":
        return False
    if schema.get("format") == "date-time":
        return "2026-01-01T00:00:00Z"
    if schema.get("format") == "date":
        return "2026-01-01"
    return "<string>"


def _schema_constraints(schema: dict[str, Any]) -> list[str]:
    labels = {
        "minimum": "Minimum",
        "maximum": "Maximum",
        "exclusiveMinimum": "Exclusive minimum",
        "exclusiveMaximum": "Exclusive maximum",
        "minLength": "Minimum length",
        "maxLength": "Maximum length",
        "minItems": "Minimum items",
        "maxItems": "Maximum items",
        "pattern": "Pattern",
    }
    constraints = [
        f"{label}: {schema[key]}" for key, label in labels.items() if key in schema
    ]
    if schema.get("nullable") is True:
        constraints.append("Nullable")
    if schema.get("readOnly") is True:
        constraints.append("Read only")
    if schema.get("writeOnly") is True:
        constraints.append("Write only")
    return constraints


def _default_label(value: Any) -> str:
    if isinstance(value, (bool, int, float)) or value is None:
        return json.dumps(value)
    return str(value)


def _schema_with_composition(
    spec: dict[str, Any],
    schema: dict[str, Any],
    *,
    seen_refs: frozenset[str],
) -> dict[str, Any]:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        if reference in seen_refs:
            return schema
        resolved = _resolve_local_ref(spec, schema)
        if not isinstance(resolved, dict):
            return schema
        return _schema_with_composition(
            spec,
            resolved,
            seen_refs=seen_refs | {reference},
        )

    merged = dict(schema)
    variants = schema.get("allOf")
    if isinstance(variants, list):
        properties: dict[str, Any] = dict(schema.get("properties") or {})
        required = list(schema.get("required") or [])
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            resolved_variant = _schema_with_composition(
                spec,
                variant,
                seen_refs=seen_refs,
            )
            properties.update(resolved_variant.get("properties") or {})
            for name in resolved_variant.get("required") or []:
                if name not in required:
                    required.append(name)
        if properties:
            merged["properties"] = properties
            merged["type"] = "object"
        if required:
            merged["required"] = required
    return merged


def _field_from_schema(
    spec: dict[str, Any],
    *,
    name: str,
    schema: Any,
    required: bool,
    location: str | None,
    depth: int,
    seen_refs: frozenset[str],
) -> ReferenceField:
    raw_schema = schema if isinstance(schema, dict) else {}
    reference = raw_schema.get("$ref")
    next_seen_refs = seen_refs
    if isinstance(reference, str):
        next_seen_refs = seen_refs | {reference}
    resolved = _schema_with_composition(
        spec,
        raw_schema,
        seen_refs=seen_refs,
    )
    description = str(resolved.get("description") or raw_schema.get("description") or "")
    child_schema: Any = resolved
    if resolved.get("type") == "array":
        child_schema = resolved.get("items")
    children: list[ReferenceField] = []
    if depth < 12 and not (isinstance(reference, str) and reference in seen_refs):
        children = _schema_fields(
            spec,
            child_schema,
            location=location,
            depth=depth + 1,
            seen_refs=next_seen_refs,
            root_value=False,
        )
    enum = resolved.get("enum")
    return ReferenceField(
        name=name,
        type_label=_type_label(spec, raw_schema),
        required=required,
        description=description,
        location=location,
        default=_default_label(resolved["default"]) if "default" in resolved else None,
        api_type_label=_playground_type_label(spec, raw_schema) if location else None,
        children=children,
        enum_values=[str(value) for value in enum] if isinstance(enum, list) else [],
        constraints=_schema_constraints(resolved),
    )


def _schema_fields(
    spec: dict[str, Any],
    schema: Any,
    *,
    location: str | None,
    depth: int = 0,
    seen_refs: frozenset[str] = frozenset(),
    root_value: bool = True,
) -> list[ReferenceField]:
    if not isinstance(schema, dict):
        return []
    resolved = _schema_with_composition(spec, schema, seen_refs=seen_refs)
    if not isinstance(resolved, dict) or depth >= 12:
        return []
    properties = resolved.get("properties")
    if not isinstance(properties, dict):
        if not root_value:
            variants = resolved.get("oneOf") or resolved.get("anyOf")
            if isinstance(variants, list):
                fields: list[ReferenceField] = []
                for index, variant in enumerate(variants, start=1):
                    if not isinstance(variant, dict):
                        continue
                    fields.append(
                        _field_from_schema(
                            spec,
                            name=_schema_name(variant, fallback=f"Variant {index}"),
                            schema=variant,
                            required=False,
                            location=location,
                            depth=depth,
                            seen_refs=seen_refs,
                        )
                    )
                return fields
            return []
        return [
            _field_from_schema(
                spec,
                name="value",
                schema=schema,
                required=True,
                location=location,
                depth=depth,
                seen_refs=seen_refs,
            )
        ]
    required = set(resolved.get("required") or [])
    return [
        _field_from_schema(
            spec,
            name=str(name),
            schema=child,
            required=name in required,
            location=location,
            depth=depth,
            seen_refs=seen_refs,
        )
        for name, child in properties.items()
    ]


def _media_schema(content: Any) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(content, dict) or not content:
        return None, None
    for preferred in ("application/json", "application/*+json"):
        media = content.get(preferred)
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            return preferred, media["schema"]
    media_type, media = next(iter(content.items()))
    if isinstance(media, dict) and isinstance(media.get("schema"), dict):
        return str(media_type), media["schema"]
    return str(media_type), None


def _media_example(content: Any, media_type: str | None) -> Any:
    if not isinstance(content, dict) or media_type is None:
        return None
    media = content.get(media_type)
    if not isinstance(media, dict):
        return None
    if "example" in media:
        return media["example"]
    examples = media.get("examples")
    if isinstance(examples, dict):
        for raw_example in examples.values():
            example = raw_example.get("value") if isinstance(raw_example, dict) else None
            if example is not None:
                return example
    return None


def _parameter_panels(
    spec: dict[str, Any], path_item: dict[str, Any], operation: dict[str, Any]
) -> list[ReferencePanel]:
    parameters = [
        *(path_item.get("parameters") or []),
        *(operation.get("parameters") or []),
    ]
    by_location: dict[str, list[ReferenceField]] = {}
    for raw_parameter in parameters:
        parameter = _resolve_local_ref(spec, raw_parameter)
        if not isinstance(parameter, dict):
            continue
        location = str(parameter.get("in") or "query")
        schema = parameter.get("schema")
        if isinstance(schema, dict) and parameter.get("description"):
            schema = {**schema, "description": str(parameter["description"])}
        field = _field_from_schema(
            spec,
            name=str(parameter.get("name") or "parameter"),
            schema=schema,
            required=bool(parameter.get("required")),
            location=location,
            depth=0,
            seen_refs=frozenset(),
        )
        by_location.setdefault(location, []).append(field)
    labels = {
        "path": "Path parameters",
        "query": "Query parameters",
        "header": "Headers",
    }
    return [
        ReferencePanel(
            title=labels.get(location, f"{location.title()} parameters"),
            schema=ReferenceSchema(
                name=labels.get(location, location.title()), fields=fields
            ),
        )
        for location, fields in by_location.items()
    ]


def _request_panel(
    spec: dict[str, Any], operation: dict[str, Any]
) -> tuple[ReferencePanel | None, Any, str | None]:
    request_body = _resolve_local_ref(spec, operation.get("requestBody"))
    if not isinstance(request_body, dict):
        return None, None, None
    content = request_body.get("content")
    media_type, schema = _media_schema(content)
    if schema is None:
        return None, None, media_type
    name = _schema_name(schema, fallback="RequestBody")
    authored_sample = _media_example(content, media_type)
    sample = authored_sample if authored_sample is not None else _example_value(spec, schema)
    panel = ReferencePanel(
        title="Body",
        description=str(request_body.get("description") or ""),
        badges=[ReferenceBadge(media_type or "body", "neutral")],
        schema=ReferenceSchema(
            name=name,
            summary=_type_label(spec, schema),
            fields=_schema_fields(spec, schema, location="body"),
        ),
    )
    return panel, sample, media_type


def _authorization_panels(
    spec: dict[str, Any], operation: dict[str, Any]
) -> list[ReferencePanel]:
    security = operation.get("security", spec.get("security"))
    if not isinstance(security, list) or not security:
        return []
    components = spec.get("components")
    schemes = components.get("securitySchemes") if isinstance(components, dict) else {}
    if not isinstance(schemes, dict):
        schemes = {}

    panels: list[ReferencePanel] = []
    seen: set[str] = set()
    for requirement in security:
        if not isinstance(requirement, dict):
            continue
        for scheme_name in requirement:
            if scheme_name in seen:
                continue
            seen.add(scheme_name)
            raw_scheme = _resolve_local_ref(spec, schemes.get(scheme_name))
            scheme = raw_scheme if isinstance(raw_scheme, dict) else {}
            scheme_type = str(scheme.get("type") or "authentication")
            parameter_name = "Authorization"
            location = "header"
            type_label = "string"
            details: list[str] = []
            if scheme_type == "http":
                http_scheme = str(scheme.get("scheme") or "").strip()
                bearer_format = str(scheme.get("bearerFormat") or "").strip()
                if http_scheme:
                    details.append(f"HTTP {http_scheme} authentication.")
                if http_scheme.casefold() == "bearer":
                    details.append(
                        "Send the token as `Authorization: Bearer <token>`."
                    )
                if bearer_format:
                    details.append(f"Bearer format: `{bearer_format}`.")
            elif scheme_type == "apiKey":
                parameter_name = str(scheme.get("name") or "apiKey")
                location = str(scheme.get("in") or "header")
                details.append(f"API key authentication in the {location}.")
            elif scheme_type in {"oauth2", "openIdConnect"}:
                details.append(f"{scheme_type} authentication.")
            authored_description = str(scheme.get("description") or "").strip()
            if authored_description:
                details.append(authored_description)
            panels.append(
                ReferencePanel(
                    title=str(scheme_name),
                    schema=ReferenceSchema(
                        name=str(scheme_name),
                        fields=[
                            ReferenceField(
                                name=parameter_name,
                                type_label=type_label,
                                required=True,
                                description=" ".join(details),
                                location=location,
                                api_type_label=type_label,
                            )
                        ],
                    ),
                )
            )
    return panels


def _response_panels(
    spec: dict[str, Any], operation: dict[str, Any]
) -> tuple[list[ReferencePanel], list[ReferenceExample]]:
    panels: list[ReferencePanel] = []
    examples: list[ReferenceExample] = []
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return panels, examples
    for status, raw_response in responses.items():
        response = _resolve_local_ref(spec, raw_response)
        if not isinstance(response, dict):
            continue
        content = response.get("content")
        media_type, schema = _media_schema(content)
        description = str(response.get("description") or "")
        fields = (
            _schema_fields(spec, schema, location=None) if schema is not None else []
        )
        schema_name = (
            _schema_name(schema, fallback=f"Response{status}")
            if schema
            else f"Response{status}"
        )
        panels.append(
            ReferencePanel(
                title=str(status),
                description=description,
                badges=[ReferenceBadge(media_type, "neutral")] if media_type else [],
                schema=ReferenceSchema(
                    name=schema_name,
                    summary=_type_label(spec, schema),
                    fields=fields,
                )
                if schema is not None
                else None,
            )
        )
        if schema is not None:
            language = "json" if media_type and "json" in media_type else "text"
            authored_sample = _media_example(content, media_type)
            sample = (
                authored_sample
                if authored_sample is not None
                else _example_value(spec, schema)
            )
            example_body = (
                json_body(sample) if language == "json" else str(sample or "")
            )
            examples.append(
                ReferenceExample(
                    title=str(status),
                    body=example_body,
                    language=language,
                    kind="response",
                    media_type=media_type,
                )
            )
    return panels, examples


def _expand_local_refs(
    spec: dict[str, Any],
    value: Any,
    *,
    seen_refs: frozenset[str] = frozenset(),
) -> Any:
    if isinstance(value, list):
        return [_expand_local_refs(spec, item, seen_refs=seen_refs) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/"):
        if reference in seen_refs:
            return {"$ref": reference}
        return {
            "$ref": reference,
            "$resolved": _expand_local_refs(
                spec,
                _resolve_local_ref(spec, value),
                seen_refs=seen_refs | {reference},
            ),
        }
    return {
        str(key): _expand_local_refs(spec, child, seen_refs=seen_refs)
        for key, child in value.items()
    }


def _operation_fingerprint(
    spec: dict[str, Any],
    operation: dict[str, Any],
    *,
    method: str,
    path: str,
) -> str:
    contract = {
        "method": method.lower(),
        "operation": operation,
        "path_parameters": _path_item(spec, path).get("parameters") or [],
    }
    return json.dumps(
        _expand_local_refs(spec, contract),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _remove_as_of(operation: dict[str, Any]) -> str | None:
    extension = operation.get("x-remove-as-of")
    if isinstance(extension, str) and extension.strip():
        return extension.strip().removeprefix("v")
    text = " ".join(str(operation.get(key) or "") for key in ("summary", "description"))
    match = REMOVE_AS_OF_RE.search(text)
    return match.group("version").removeprefix("v") if match else None


def _operation_id(operation: dict[str, Any]) -> str | None:
    value = operation.get("operationId")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _operations_by_id(
    spec: dict[str, Any],
) -> dict[str, tuple[str, str, dict[str, Any]]]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI specification must define paths")
    indexed: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {
                "get",
                "put",
                "post",
                "delete",
                "options",
                "head",
                "patch",
                "trace",
            } or not isinstance(operation, dict):
                continue
            operation_id = _operation_id(operation)
            if operation_id is None:
                continue
            if operation_id in indexed:
                previous_method, previous_path, _previous = indexed[operation_id]
                raise ValueError(
                    "Duplicate OpenAPI operationId "
                    f"'{operation_id}': {previous_method.upper()} {previous_path} and "
                    f"{method.upper()} {path}"
                )
            indexed[operation_id] = (method.lower(), path, operation)
    return indexed


def _humanized_operation_id(operation: dict[str, Any]) -> str | None:
    operation_id = _operation_id(operation)
    if operation_id is None:
        return None
    title = re.sub(
        rf"^(?:{'|'.join(('get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace'))})",
        "",
        operation_id,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"^V\d+", "", title)
    title = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", title)
    title = re.sub(r"[-_]+", " ", title)
    title = " ".join(title.split())
    title = re.sub(
        r"\s+(?:at|by|for|from|to|with)$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return title[0].upper() + title[1:].lower() if title else None


def _describes_operation(text: str) -> bool:
    return not LIFECYCLE_TITLE_RE.match(text.strip())


def _operation_title(operation: dict[str, Any], *, method: str, path: str) -> str:
    summary = str(operation.get("summary") or "").strip()
    mintlify_path = re.sub(r"\{([^{}]+)\}", r":\1", path)
    generated_summaries = {
        path,
        f"{method.upper()} {path}",
        f"{method.upper()} {mintlify_path}",
    }
    if (
        summary
        and summary not in generated_summaries
        and _describes_operation(summary)
    ):
        return summary
    description = " ".join(str(operation.get("description") or "").split())
    first_sentence = description.partition(".")[0].strip()
    if (
        first_sentence
        and len(first_sentence) <= 96
        and _describes_operation(first_sentence)
    ):
        return first_sentence
    operation_id_title = _humanized_operation_id(operation)
    if operation_id_title is not None:
        return operation_id_title
    return f"{method.upper()} {path}"


def _operation_overview(operation: dict[str, Any], *, limit: int = 460) -> str:
    description = " ".join(str(operation.get("description") or "").split())
    if len(description) <= limit:
        return description
    sentence_end = description.rfind(". ", 0, limit)
    if sentence_end >= 0:
        return description[: sentence_end + 1]
    return description


def operation_history_events(
    *,
    specs_by_version: dict[str, dict[str, Any]],
    versions: list[str],
    publish_version: str,
    method: str,
    path: str,
    source_name: str,
) -> list[HistoryEvent]:
    published = _operation(specs_by_version[publish_version], method, path)
    published_operation_id = _operation_id(published)
    observed: list[tuple[str, str, str, dict[str, Any]]] = []
    for version in versions:
        if published_operation_id is not None:
            located = _operations_by_id(specs_by_version[version]).get(
                published_operation_id
            )
            if located is not None:
                observed_method, observed_path, observed_operation = located
                observed.append(
                    (version, observed_method, observed_path, observed_operation)
                )
                continue
            try:
                observed.append(
                    (
                        version,
                        method.lower(),
                        path,
                        _operation(specs_by_version[version], method, path),
                    )
                )
            except ValueError:
                continue
        else:
            try:
                observed.append(
                    (
                        version,
                        method.lower(),
                        path,
                        _operation(specs_by_version[version], method, path),
                    )
                )
            except ValueError:
                continue
    if not observed:
        raise ValueError(
            f"Operation is absent from all comparison versions: {method.upper()} {path}"
        )

    events: list[HistoryEvent] = []
    remove_as_of = _remove_as_of(published)
    if remove_as_of is not None:
        evidence = Evidence(
            kind=EvidenceKind.SOURCE_METADATA,
            source=source_name,
            observed_in_version=publish_version,
            location=f"paths.{path}.{method.lower()}.description",
            detail="Authored removal schedule in the OpenAPI operation description.",
        )
        events.append(
            HistoryEvent(
                kind=HistoryEventKind.REMOVE_AS_OF,
                version=remove_as_of,
                label="Removal scheduled",
                details=(),
                evidence=(evidence,),
            )
        )

    deprecated_observation = next(
        (
            (version, observed_method, observed_path)
            for version, observed_method, observed_path, operation in observed
            if operation.get("deprecated") is True
        ),
        None,
    )
    if deprecated_observation is not None:
        deprecated_version, deprecated_method, deprecated_path = deprecated_observation
        evidence = Evidence(
            kind=EvidenceKind.SOURCE_METADATA,
            source=source_name,
            observed_in_version=deprecated_version,
            location=f"paths.{deprecated_path}.{deprecated_method}.deprecated",
        )
        events.append(
            HistoryEvent(
                kind=HistoryEventKind.DEPRECATED,
                version=deprecated_version,
                label="Deprecated",
                details=(),
                evidence=(evidence,),
            )
        )

    previous_fingerprint: str | None = None
    previous_location: tuple[str, str] | None = None
    for version, observed_method, observed_path, operation in observed:
        fingerprint = _operation_fingerprint(
            specs_by_version[version],
            operation,
            method=observed_method,
            path=observed_path,
        )
        location = (observed_method, observed_path)
        if previous_fingerprint is not None and (
            fingerprint != previous_fingerprint or location != previous_location
        ):
            if previous_location is not None and location != previous_location:
                prior_method, prior_path = previous_location
                details = (
                    f"The operation moved from {prior_method.upper()} {prior_path} "
                    f"to {observed_method.upper()} {observed_path}.",
                )
            else:
                details = (
                    f"The {observed_method.upper()} {observed_path} operation was updated "
                    "in this snapshot.",
                )
            evidence = Evidence(
                kind=EvidenceKind.SNAPSHOT_DIFF,
                source=source_name,
                observed_in_version=version,
                location=f"paths.{observed_path}.{observed_method}",
            )
            events.append(
                HistoryEvent(
                    kind=HistoryEventKind.CHANGED,
                    version=version,
                    label="Updated",
                    details=details,
                    evidence=(evidence,),
                )
            )
        previous_fingerprint = fingerprint
        previous_location = location

    first_version, first_method, first_path, _first_operation = observed[0]
    introduction = Evidence(
        kind=EvidenceKind.SNAPSHOT,
        source=source_name,
        observed_in_version=first_version,
        location=f"paths.{first_path}.{first_method}",
    )
    events.append(
        HistoryEvent(
            kind=HistoryEventKind.INTRODUCED,
            version=first_version,
            label="Added",
            details=(),
            evidence=(introduction,),
        )
    )

    replacement = published.get("x-replaces")
    if isinstance(replacement, str) and replacement.strip():
        evidence = Evidence(
            kind=EvidenceKind.SOURCE_METADATA,
            source=source_name,
            observed_in_version=publish_version,
            location=f"paths.{path}.{method.lower()}.x-replaces",
        )
        events.append(
            HistoryEvent(
                kind=HistoryEventKind.REPLACEMENT,
                version=first_version,
                label="Replacement",
                details=(f"Replaces {replacement.strip()}.",),
                evidence=(evidence,),
            )
        )

    version_order = {version: index for index, version in enumerate(versions)}
    kind_order = {
        HistoryEventKind.REMOVE_AS_OF: 0,
        HistoryEventKind.DEPRECATED: 1,
        HistoryEventKind.CHANGED: 2,
        HistoryEventKind.INTRODUCED: 3,
        HistoryEventKind.REPLACEMENT: 4,
    }

    def sort_key(event: HistoryEvent) -> tuple[int, int, str]:
        index = version_order.get(event.version, len(versions))
        return (-index, kind_order[event.kind], event.version)

    return sorted(events, key=sort_key)


def _request_examples(
    *,
    method: str,
    server: str,
    path: str,
    media_type: str | None,
    sample: Any,
    auth_method: str | None,
) -> list[ReferenceExample]:
    if auth_method not in {None, "bearer"}:
        raise ValueError(
            f"Unsupported manual OpenAPI authentication method: {auth_method}"
        )
    url = f"{server.rstrip('/')}{path}"
    content_type = media_type or "application/json"
    lines = [
        f"curl --request {method.upper()} \\",
        f"  --url '{url}' \\",
    ]
    if auth_method == "bearer":
        lines.append("  --header 'Authorization: Bearer $TOKEN' \\")
    if sample is not None:
        lines.append(f"  --header 'Content-Type: {content_type}' \\")
        if media_type == "application/octet-stream":
            lines.append("  --data-binary '@request.bin'")
        else:
            shell_sample = json_body(sample).replace("'", "'\"'\"'")
            lines.append(f"  --data '{shell_sample}'")
    if lines[-1].endswith(" \\"):
        lines[-1] = lines[-1].removesuffix(" \\")
    curl = ReferenceExample(
        title="cURL", body="\n".join(lines), language="bash", kind="request"
    )
    if media_type == "application/octet-stream":
        return [curl]

    headers: dict[str, str] = {}
    if auth_method == "bearer":
        headers["Authorization"] = "Bearer <token>"
    if sample is not None:
        headers["Content-Type"] = content_type
    pretty_sample = json_body(sample) if sample is not None else ""

    python_lines = ["import json", "import requests", "", f'url = "{url}"']
    if headers:
        python_lines.append(f"headers = {headers!r}")
    if sample is not None:
        python_lines.extend(
            [
                f"payload = json.loads(r'''{pretty_sample}''')",
                "response = requests.request(",
                f'    "{method.upper()}", url, headers=headers, json=payload',
                ")",
            ]
        )
    else:
        header_arg = ", headers=headers" if headers else ""
        python_lines.append(
            f'response = requests.request("{method.upper()}", url{header_arg})'
        )
    python_lines.extend(["", "print(response.text)"])

    js_headers = json.dumps(headers, ensure_ascii=False, indent=2)
    javascript_lines = [
        f"const response = await fetch('{url}', {{",
        f"  method: '{method.upper()}',",
    ]
    if headers:
        javascript_lines.append(f"  headers: {js_headers},")
    if sample is not None:
        javascript_lines.append(f"  body: JSON.stringify({pretty_sample}),")
    javascript_lines.extend(["});", "", "console.log(await response.text());"])

    php_headers = ",\n        ".join(
        json.dumps(f"{name}: {value}") for name, value in headers.items()
    )
    php_lines = ["<?php", "$curl = curl_init();", "", "curl_setopt_array($curl, ["]
    php_lines.extend(
        [
            f"    CURLOPT_URL => '{url}',",
            "    CURLOPT_RETURNTRANSFER => true,",
            f"    CURLOPT_CUSTOMREQUEST => '{method.upper()}',",
        ]
    )
    if sample is not None:
        php_lines.append(f"    CURLOPT_POSTFIELDS => <<<'JSON'\n{pretty_sample}\nJSON,")
    if headers:
        php_lines.append(f"    CURLOPT_HTTPHEADER => [\n        {php_headers}\n    ],")
    php_lines.extend(["]);", "", "$response = curl_exec($curl);", "echo $response;"])

    go_headers = [
        f'req.Header.Set("{name}", "{value}")' for name, value in headers.items()
    ]
    escaped_go_sample = pretty_sample.replace(chr(96), "\\" + chr(96))
    go_body = (
        f"bytes.NewBufferString({chr(96)}{escaped_go_sample}{chr(96)})"
        if sample is not None
        else "nil"
    )
    go_imports = ['  "fmt"', '  "io"', '  "net/http"']
    if sample is not None:
        go_imports.insert(0, '  "bytes"')
    go_lines = [
        "package main",
        "",
        "import (",
        *go_imports,
        ")",
        "",
        "func main() {",
        f'  req, _ := http.NewRequest("{method.upper()}", "{url}", {go_body})',
        *(f"  {line}" for line in go_headers),
        "  response, _ := http.DefaultClient.Do(req)",
        "  defer response.Body.Close()",
        "  body, _ := io.ReadAll(response.Body)",
        "  fmt.Println(string(body))",
        "}",
    ]

    java_lines = [
        "import java.net.URI;",
        "import java.net.http.HttpClient;",
        "import java.net.http.HttpRequest;",
        "import java.net.http.HttpResponse;",
        "",
        "var request = HttpRequest.newBuilder()",
        f'    .uri(URI.create("{url}"))',
    ]
    for name, value in headers.items():
        java_lines.append(f'    .header("{name}", "{value}")')
    body_publisher = (
        f'HttpRequest.BodyPublishers.ofString("""\n{pretty_sample}\n""")'
        if sample is not None
        else "HttpRequest.BodyPublishers.noBody()"
    )
    java_lines.extend(
        [
            f'    .method("{method.upper()}", {body_publisher})',
            "    .build();",
            "var response = HttpClient.newHttpClient().send(",
            "    request, HttpResponse.BodyHandlers.ofString());",
            "System.out.println(response.body());",
        ]
    )

    ruby_lines = [
        "require 'net/http'",
        "require 'uri'",
        "",
        f"uri = URI('{url}')",
        f"request = Net::HTTP::{method.title()}.new(uri)",
    ]
    for name, value in headers.items():
        ruby_lines.append(f"request['{name}'] = '{value}'")
    if sample is not None:
        ruby_lines.extend(["request.body = <<~JSON", pretty_sample, "JSON"])
    ruby_lines.extend(
        [
            "response = Net::HTTP.start(uri.hostname, uri.port) do |http|",
            "  http.request(request)",
            "end",
            "puts response.body",
        ]
    )

    return [
        curl,
        ReferenceExample("Python", "\n".join(python_lines), "python", "request"),
        ReferenceExample(
            "JavaScript", "\n".join(javascript_lines), "javascript", "request"
        ),
        ReferenceExample("PHP", "\n".join(php_lines), "php", "request"),
        ReferenceExample("Go", "\n".join(go_lines), "go", "request"),
        ReferenceExample("Java", "\n".join(java_lines), "java", "request"),
        ReferenceExample("Ruby", "\n".join(ruby_lines), "ruby", "request"),
    ]


def render_manual_openapi_operation(
    *,
    spec: dict[str, Any],
    options: ManualOpenAPIRenderOptions,
    history_events: list[HistoryEvent],
    publish_version: str,
) -> Any:
    method = options.method.upper()
    operation = _operation(spec, method, options.path)
    path_item = _path_item(spec, options.path)
    summary = _operation_title(operation, method=method, path=options.path)
    description = _operation_overview(operation)
    mintlify_path = re.sub(r"\{([^{}]+)\}", r":\1", options.path)
    page_title = f"{method} {mintlify_path}"
    declared_security = operation.get("security", spec.get("security"))
    effective_auth_method = (
        None if declared_security == [] else options.auth_method
    )

    authorizations = _authorization_panels(spec, operation)
    inputs = _parameter_panels(spec, path_item, operation)
    request_panel, request_sample, request_media_type = _request_panel(spec, operation)
    if request_panel is not None:
        inputs.append(request_panel)
    outputs, response_examples = _response_panels(spec, operation)
    examples = [
        *_request_examples(
            method=method,
            server=options.server,
            path=options.path,
            media_type=request_media_type,
            sample=request_sample,
            auth_method=effective_auth_method,
        ),
        *response_examples,
    ]

    badges = reference_badges_for_history_events(
        history_events,
        kind_label="OpenAPI",
    )

    api_path = f"{method} {options.server.rstrip('/')}{options.path}"
    protocol_items = [
        ReferenceMetaItem("Operation ID", str(operation.get("operationId") or "-")),
        ReferenceMetaItem("Published", publish_version),
    ]
    if (
        effective_auth_method is not None
        and options.authentication_label is not None
    ):
        protocol_items.insert(
            1, ReferenceMetaItem("Authentication", options.authentication_label)
        )
    if options.raw_spec_href is not None:
        protocol_items.append(
            ReferenceMetaItem(
                "Specification", "Download OpenAPI", href=options.raw_spec_href
            )
        )
    return render_operation_page(
        ReferenceOperationPage(
            path=options.output_path,
            title=page_title,
            description=description or summary,
            eyebrow=options.surface_label,
            summary=description or summary,
            breadcrumbs=list(options.breadcrumbs),
            badges=badges,
            operation_method=method,
            operation_target=options.path,
            protocol_items=protocol_items,
            authorizations=authorizations,
            inputs=inputs,
            outputs=outputs,
            examples=examples,
            history_events=history_events,
            api_frontmatter=api_path,
            auth_method=effective_auth_method,
            playground=options.playground,
        )
    )
