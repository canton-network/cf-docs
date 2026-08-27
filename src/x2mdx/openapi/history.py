from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from x2mdx.history.models import (
    ChangeDetail,
    Evidence,
    EvidenceKind,
    HistoryItem,
    HistoryMode,
    IdentityConfidence,
    LifecycleState,
    LifecycleTransition,
    ReferenceFormat,
    ReplacementEdge,
    SourceArtifact,
    SurfaceHistoryReport,
    VersionSelectionPolicy,
)


HTTP_METHODS = {
    "get",
    "put",
    "post",
    "delete",
    "options",
    "head",
    "patch",
    "trace",
}
REMOVE_AS_OF_RE = re.compile(
    r"\b(?:will\s+be\s+)?removed\s+in\s+(?:the\s+)?(?:Canton\s+)?version\s+"
    r"(?P<version>v?\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OpenAPIHistoryScope:
    """One identity namespace within a combined OpenAPI history report."""

    id: str
    specs_by_version: Mapping[str, dict[str, Any]]
    current_routes: Mapping[tuple[str, str], str] = field(default_factory=dict)


@dataclass(frozen=True)
class _OperationSnapshot:
    version: str
    method: str
    path: str
    operation: dict[str, Any]
    fingerprint: str
    used_fallback_identity: bool


def build_openapi_history_report(
    *,
    surface_id: str,
    title: str,
    configured_scope: str,
    scopes: tuple[OpenAPIHistoryScope, ...],
    comparison_versions: tuple[str, ...],
    publish_version: str,
    source_artifacts: tuple[SourceArtifact, ...],
    version_policy: VersionSelectionPolicy,
    limitations: tuple[str, ...] = (),
) -> SurfaceHistoryReport:
    if not scopes:
        raise ValueError("OpenAPI history requires at least one configured scope")
    scope_ids = [scope.id for scope in scopes]
    if len(scope_ids) != len(set(scope_ids)):
        raise ValueError("OpenAPI history scope IDs must be unique")

    sources_by_version = _sources_by_version(source_artifacts)
    missing_sources = tuple(
        version for version in comparison_versions if version not in sources_by_version
    )
    if missing_sources:
        raise ValueError(
            "OpenAPI history requires a source artifact for every comparison "
            f"version: {', '.join(missing_sources)}"
        )
    items: list[HistoryItem] = []
    used_fallback = False
    for scope in scopes:
        scope_items = _history_items_for_scope(
            scope=scope,
            comparison_versions=comparison_versions,
            publish_version=publish_version,
            sources_by_version=sources_by_version,
        )
        items.extend(scope_items)
        used_fallback = used_fallback or any(
            item.identity_confidence == IdentityConfidence.FALLBACK
            for item in scope_items
        )

    report_limitations = list(limitations)
    for scope in scopes:
        missing_versions = tuple(
            version
            for version in comparison_versions
            if version not in scope.specs_by_version
        )
        if missing_versions:
            report_limitations.append(
                f"{scope.id} is absent from {len(missing_versions)} selected release "
                f"snapshot(s): {', '.join(missing_versions)}. Its operation history "
                "uses only releases that contain the specification."
            )
    if used_fallback:
        report_limitations.append(
            "Some snapshots omit operationId; identity falls back to METHOD path "
            "within that OpenAPI specification and is recorded as lower confidence."
        )

    return SurfaceHistoryReport(
        surface_id=surface_id,
        title=title,
        format=ReferenceFormat.OPENAPI,
        configured_scope=configured_scope,
        history_mode=HistoryMode.SNAPSHOTS,
        publish_version=publish_version,
        comparison_versions=comparison_versions,
        source_artifacts=source_artifacts,
        version_policy=version_policy,
        items=tuple(sorted(items, key=lambda item: item.id)),
        limitations=tuple(report_limitations),
    )


def _history_items_for_scope(
    *,
    scope: OpenAPIHistoryScope,
    comparison_versions: tuple[str, ...],
    publish_version: str,
    sources_by_version: Mapping[str, str],
) -> list[HistoryItem]:
    if publish_version not in scope.specs_by_version:
        raise ValueError(
            f"OpenAPI history scope {scope.id} is absent from publish version "
            f"{publish_version}"
        )
    available_versions = tuple(
        version for version in comparison_versions if version in scope.specs_by_version
    )
    observations = _observations_by_identity(
        scope=scope,
        comparison_versions=comparison_versions,
    )
    known_item_ids = {
        _scoped_item_id(scope_id=scope.id, local_id=local_id)
        for local_id in observations
    }
    items = [
        _history_item(
            scope=scope,
            local_id=local_id,
            observations=item_observations,
            available_versions=available_versions,
            publish_version=publish_version,
            sources_by_version=sources_by_version,
            known_item_ids=known_item_ids,
        )
        for local_id, item_observations in observations.items()
    ]
    edges_by_item_id: dict[str, list[ReplacementEdge]] = {
        item.id: list(item.replacement_edges) for item in items
    }
    all_edges = {
        (edge.from_item_id, edge.to_item_id, edge.version): edge
        for item in items
        for edge in item.replacement_edges
    }
    for edge in all_edges.values():
        for endpoint in (edge.from_item_id, edge.to_item_id):
            endpoint_edges = edges_by_item_id[endpoint]
            if edge not in endpoint_edges:
                endpoint_edges.append(edge)
    return [
        replace(item, replacement_edges=tuple(edges_by_item_id[item.id]))
        for item in items
    ]


def _history_item(
    *,
    scope: OpenAPIHistoryScope,
    local_id: str,
    observations: list[_OperationSnapshot],
    available_versions: tuple[str, ...],
    publish_version: str,
    sources_by_version: Mapping[str, str],
    known_item_ids: set[str],
) -> HistoryItem:
    item_id = _scoped_item_id(scope_id=scope.id, local_id=local_id)
    first = observations[0]
    last = observations[-1]
    current = next(
        (
            observation
            for observation in observations
            if observation.version == publish_version
        ),
        None,
    )
    current_present = current is not None
    observation_indexes = [
        available_versions.index(observation.version) for observation in observations
    ]
    if any(
        right - left > 1
        for left, right in zip(observation_indexes, observation_indexes[1:])
    ):
        raise ValueError(
            f"OpenAPI operation disappears and later reappears within {scope.id}: "
            f"{item_id}. The normalized history model cannot represent this "
            "continuity without an explicit reintroduction event."
        )
    location_observation = current or last
    route = None
    if current is not None:
        route = scope.current_routes.get((current.method, current.path))
        if route is None:
            raise ValueError(
                f"Current OpenAPI operation has no configured reader route: "
                f"{scope.id} {current.method.upper()} {current.path}"
            )

    introduction_evidence = _evidence(
        kind=EvidenceKind.SNAPSHOT,
        source=sources_by_version[first.version],
        version=first.version,
        scope_id=scope.id,
        method=first.method,
        path=first.path,
    )
    changes = _changes(
        scope_id=scope.id,
        observations=observations,
        sources_by_version=sources_by_version,
    )
    lifecycle_transitions = _lifecycle_transitions(
        scope_id=scope.id,
        observations=observations,
        sources_by_version=sources_by_version,
    )
    remove_as_of, remove_as_of_evidence = _authored_remove_as_of(
        scope_id=scope.id,
        observations=observations,
        sources_by_version=sources_by_version,
    )
    replacement_edges = _replacement_edges(
        scope_id=scope.id,
        item_id=item_id,
        observations=observations,
        sources_by_version=sources_by_version,
        known_item_ids=known_item_ids,
    )

    observed_removal = None
    removal_evidence = None
    if not current_present:
        last_index = available_versions.index(last.version)
        observed_removal = available_versions[last_index + 1]
        removal_evidence = Evidence(
            kind=EvidenceKind.SNAPSHOT_DIFF,
            source=sources_by_version[observed_removal],
            observed_in_version=observed_removal,
            location=scope.id,
            detail=(
                f"{last.method.upper()} {last.path} is absent from this specification snapshot."
            ),
        )

    identity_evidence = tuple(
        _evidence(
            kind=EvidenceKind.SNAPSHOT,
            source=sources_by_version[observation.version],
            version=observation.version,
            scope_id=scope.id,
            method=observation.method,
            path=observation.path,
            detail="operationId was absent; identity used the METHOD path fallback.",
        )
        for observation in observations
        if observation.used_fallback_identity
    )
    identity_confidence = (
        IdentityConfidence.FALLBACK if identity_evidence else IdentityConfidence.EXACT
    )
    lifecycle_state = lifecycle_transitions[-1].state if lifecycle_transitions else None

    return HistoryItem(
        id=item_id,
        kind="operation",
        route=route,
        location=(
            f"{scope.id}: {location_observation.method.upper()} "
            f"{location_observation.path}"
        ),
        first_seen=first.version,
        last_seen=last.version,
        current_present=current_present,
        introduction_evidence=introduction_evidence,
        observed_removal=observed_removal,
        removal_evidence=removal_evidence,
        last_changed=changes[-1].version if changes else None,
        changes=changes,
        lifecycle_state=lifecycle_state,
        lifecycle_transitions=lifecycle_transitions,
        remove_as_of=remove_as_of,
        remove_as_of_evidence=remove_as_of_evidence,
        replacement_edges=replacement_edges,
        identity_confidence=identity_confidence,
        identity_evidence=identity_evidence,
    )


def _observations_by_identity(
    *,
    scope: OpenAPIHistoryScope,
    comparison_versions: tuple[str, ...],
) -> dict[str, list[_OperationSnapshot]]:
    raw_by_version: dict[str, list[tuple[str, str, dict[str, Any], str | None]]] = {}
    explicit_ids_by_location: dict[tuple[str, str], set[str]] = {}
    for version in comparison_versions:
        spec = scope.specs_by_version.get(version)
        if spec is None:
            continue
        raw_operations: list[tuple[str, str, dict[str, Any], str | None]] = []
        seen_operation_ids: dict[str, tuple[str, str]] = {}
        for method, path, operation in _operation_items(spec):
            operation_id = _operation_id(operation)
            if operation_id is not None:
                if operation_id in seen_operation_ids:
                    previous_method, previous_path = seen_operation_ids[operation_id]
                    raise ValueError(
                        "Duplicate OpenAPI operationId "
                        f"'{operation_id}' in {scope.id} {version}: "
                        f"{previous_method.upper()} {previous_path} and "
                        f"{method.upper()} {path}"
                    )
                seen_operation_ids[operation_id] = (method, path)
                explicit_ids_by_location.setdefault((method, path), set()).add(
                    operation_id
                )
            raw_operations.append((method, path, operation, operation_id))
        raw_by_version[version] = raw_operations

    observations: dict[str, list[_OperationSnapshot]] = {}
    for version in comparison_versions:
        spec = scope.specs_by_version.get(version)
        if spec is None:
            continue
        seen_local_ids: set[str] = set()
        for method, path, operation, operation_id in raw_by_version[version]:
            used_fallback = operation_id is None
            local_id = operation_id
            if local_id is None:
                location_ids = explicit_ids_by_location.get((method, path), set())
                local_id = (
                    next(iter(location_ids))
                    if len(location_ids) == 1
                    else _fallback_operation_id(method=method, path=path)
                )
            if local_id in seen_local_ids:
                raise ValueError(
                    f"OpenAPI history identity collision in {scope.id} {version}: {local_id}"
                )
            seen_local_ids.add(local_id)
            observations.setdefault(local_id, []).append(
                _OperationSnapshot(
                    version=version,
                    method=method,
                    path=path,
                    operation=operation,
                    fingerprint=_operation_fingerprint(
                        spec,
                        operation,
                        method=method,
                        path=path,
                    ),
                    used_fallback_identity=used_fallback,
                )
            )
    return observations


def _changes(
    *,
    scope_id: str,
    observations: list[_OperationSnapshot],
    sources_by_version: Mapping[str, str],
) -> tuple[ChangeDetail, ...]:
    changes: list[ChangeDetail] = []
    previous = observations[0]
    for observation in observations[1:]:
        previous_location = (previous.method, previous.path)
        location = (observation.method, observation.path)
        if (
            observation.fingerprint == previous.fingerprint
            and location == previous_location
        ):
            previous = observation
            continue
        if location != previous_location:
            summary = (
                f"The operation moved from {previous.method.upper()} {previous.path} "
                f"to {observation.method.upper()} {observation.path}."
            )
        else:
            summary = (
                f"The {observation.method.upper()} {observation.path} operation "
                "was updated in this snapshot."
            )
        changes.append(
            ChangeDetail(
                version=observation.version,
                summary=summary,
                evidence=(
                    _evidence(
                        kind=EvidenceKind.SNAPSHOT_DIFF,
                        source=sources_by_version[observation.version],
                        version=observation.version,
                        scope_id=scope_id,
                        method=observation.method,
                        path=observation.path,
                    ),
                ),
            )
        )
        previous = observation
    return tuple(changes)


def _lifecycle_transitions(
    *,
    scope_id: str,
    observations: list[_OperationSnapshot],
    sources_by_version: Mapping[str, str],
) -> tuple[LifecycleTransition, ...]:
    transitions: list[LifecycleTransition] = []
    previous_state: LifecycleState | None = None
    for observation in observations:
        state, field_name = _authored_lifecycle_state(observation.operation)
        if state is None or state == previous_state:
            continue
        transitions.append(
            LifecycleTransition(
                state=state,
                version=observation.version,
                evidence=_evidence(
                    kind=EvidenceKind.SOURCE_METADATA,
                    source=sources_by_version[observation.version],
                    version=observation.version,
                    scope_id=scope_id,
                    method=observation.method,
                    path=observation.path,
                    field_name=field_name,
                ),
            )
        )
        previous_state = state
    return tuple(transitions)


def _authored_remove_as_of(
    *,
    scope_id: str,
    observations: list[_OperationSnapshot],
    sources_by_version: Mapping[str, str],
) -> tuple[str | None, Evidence | None]:
    observation = observations[-1]
    value = _remove_as_of(observation.operation)
    if value is None:
        return None, None
    if isinstance(observation.operation.get("x-remove-as-of"), str):
        field_name = "x-remove-as-of"
        detail = "Authored removal schedule in the OpenAPI extension."
    else:
        field_name = "description"
        detail = "Authored removal schedule in the OpenAPI operation text."
    return value, _evidence(
        kind=EvidenceKind.SOURCE_METADATA,
        source=sources_by_version[observation.version],
        version=observation.version,
        scope_id=scope_id,
        method=observation.method,
        path=observation.path,
        field_name=field_name,
        detail=detail,
    )


def _replacement_edges(
    *,
    scope_id: str,
    item_id: str,
    observations: list[_OperationSnapshot],
    sources_by_version: Mapping[str, str],
    known_item_ids: set[str],
) -> tuple[ReplacementEdge, ...]:
    edges: list[ReplacementEdge] = []
    seen_targets: set[str] = set()
    for observation in observations:
        replacement = observation.operation.get("x-replaces")
        if not isinstance(replacement, str) or not replacement.strip():
            continue
        from_item_id = _scoped_item_id(
            scope_id=scope_id,
            local_id=replacement.strip(),
        )
        if from_item_id in seen_targets:
            continue
        if from_item_id not in known_item_ids:
            raise ValueError(
                f"{item_id} x-replaces references an operation outside the "
                f"comparison window: {replacement.strip()}"
            )
        seen_targets.add(from_item_id)
        edges.append(
            ReplacementEdge(
                from_item_id=from_item_id,
                to_item_id=item_id,
                version=observation.version,
                evidence=_evidence(
                    kind=EvidenceKind.SOURCE_METADATA,
                    source=sources_by_version[observation.version],
                    version=observation.version,
                    scope_id=scope_id,
                    method=observation.method,
                    path=observation.path,
                    field_name="x-replaces",
                ),
            )
        )
    return tuple(edges)


def _sources_by_version(
    source_artifacts: tuple[SourceArtifact, ...],
) -> dict[str, str]:
    sources: dict[str, str] = {}
    for artifact in source_artifacts:
        if artifact.version in sources:
            raise ValueError(
                f"OpenAPI history has duplicate source artifacts for {artifact.version}"
            )
        sources[artifact.version] = artifact.source
    return sources


def _operation_items(
    spec: dict[str, Any],
) -> list[tuple[str, str, dict[str, Any]]]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI specification must define paths")
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            normalized_method = method.lower()
            if normalized_method in HTTP_METHODS and isinstance(operation, dict):
                operations.append((normalized_method, path, operation))
    return operations


def _operation_fingerprint(
    spec: dict[str, Any],
    operation: dict[str, Any],
    *,
    method: str,
    path: str,
) -> str:
    paths = spec.get("paths")
    path_item = paths.get(path) if isinstance(paths, dict) else None
    path_parameters = (
        path_item.get("parameters") if isinstance(path_item, dict) else None
    ) or []
    contract = {
        "method": method.lower(),
        "operation": operation,
        "path_parameters": path_parameters,
    }
    return json.dumps(
        _expand_local_refs(spec, contract),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


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
        resolved = _resolve_local_ref(spec, reference)
        return {
            "$ref": reference,
            "$resolved": _expand_local_refs(
                spec,
                resolved,
                seen_refs=seen_refs | {reference},
            ),
        }
    return {
        str(key): _expand_local_refs(spec, child, seen_refs=seen_refs)
        for key, child in value.items()
    }


def _resolve_local_ref(spec: dict[str, Any], reference: str) -> Any:
    current: Any = spec
    for token in reference[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f"Unresolvable local OpenAPI reference: {reference}")
        current = current[token]
    return current


def _operation_id(operation: dict[str, Any]) -> str | None:
    value = operation.get("operationId")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _fallback_operation_id(*, method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def _scoped_item_id(*, scope_id: str, local_id: str) -> str:
    return f"{scope_id}::{local_id}"


def _remove_as_of(operation: dict[str, Any]) -> str | None:
    extension = operation.get("x-remove-as-of")
    if isinstance(extension, str) and extension.strip():
        return extension.strip().removeprefix("v")
    text = " ".join(str(operation.get(key) or "") for key in ("summary", "description"))
    match = REMOVE_AS_OF_RE.search(text)
    return match.group("version").removeprefix("v") if match else None


def _authored_lifecycle_state(
    operation: dict[str, Any],
) -> tuple[LifecycleState | None, str]:
    raw_state = operation.get("x-state")
    if raw_state is not None:
        if not isinstance(raw_state, str):
            raise ValueError("OpenAPI x-state must be a string")
        try:
            return LifecycleState(raw_state.strip().lower()), "x-state"
        except ValueError as error:
            allowed = ", ".join(state.value for state in LifecycleState)
            raise ValueError(
                f"Unsupported OpenAPI x-state '{raw_state}'; expected one of {allowed}"
            ) from error
    if operation.get("deprecated") is True:
        return LifecycleState.DEPRECATED, "deprecated"
    return None, ""


def _evidence(
    *,
    kind: EvidenceKind,
    source: str,
    version: str,
    scope_id: str,
    method: str,
    path: str,
    field_name: str | None = None,
    detail: str | None = None,
) -> Evidence:
    suffix = f".{field_name}" if field_name else ""
    return Evidence(
        kind=kind,
        source=source,
        observed_in_version=version,
        location=f"{scope_id}#paths.{path}.{method}{suffix}",
        detail=detail,
    )
