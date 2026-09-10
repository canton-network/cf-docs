from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from x2mdx.history.models import (
    ChangeDetail,
    Evidence,
    EvidenceKind,
    HistoryItem,
    HistoryMode,
    LifecycleState,
    LifecycleTransition,
    ReferenceFormat,
    ReplacementEdge,
    SourceArtifact,
    SurfaceHistoryReport,
    VersionSelectionPolicy,
)
from x2mdx.openrpc.lifecycle import (
    build_version_doc_index,
    describe_method_changes,
    extract_method_detail,
    version_key,
)
from x2mdx.openrpc.models import OpenRpcMethodDetail, OpenRpcSourceSnapshot


@dataclass(frozen=True)
class _MethodObservation:
    version: str
    spec_id: str
    source_path: str
    detail: OpenRpcMethodDetail


def openrpc_item_id(spec_id: str, method: str) -> str:
    return f"{spec_id}#{method}"


def build_openrpc_history_report(
    *,
    sources: list[OpenRpcSourceSnapshot],
    routes: Mapping[tuple[str, str], str],
    publish_version: str | None = None,
    surface_id: str = "wallet-gateway-openrpc",
    title: str = "Wallet Gateway OpenRPC",
    configured_scope: str = "Wallet Gateway OpenRPC methods",
) -> SurfaceHistoryReport:
    if not sources:
        raise ValueError("OpenRPC history requires at least one snapshot")

    ordered_versions = tuple(sorted({source.version for source in sources}, key=version_key))
    selected_publish_version = publish_version or ordered_versions[-1]
    if selected_publish_version not in ordered_versions:
        raise ValueError(
            f"Publish version '{selected_publish_version}' is not present in selected snapshots: {list(ordered_versions)}"
        )
    comparison_versions = ordered_versions[: ordered_versions.index(selected_publish_version) + 1]
    scoped_sources = [source for source in sources if source.version in comparison_versions]
    doc_index = build_version_doc_index(scoped_sources)

    observations: dict[str, list[_MethodObservation]] = {}
    for source in sorted(scoped_sources, key=lambda item: (version_key(item.version), item.spec_id)):
        details = extract_method_detail(
            source.document,
            doc_index=doc_index[source.version],
            current_source_path=source.source_path,
        )
        for method, detail in details.items():
            item_id = openrpc_item_id(source.spec_id, method)
            observations.setdefault(item_id, []).append(
                _MethodObservation(
                    version=source.version,
                    spec_id=source.spec_id,
                    source_path=source.source_path,
                    detail=detail,
                )
            )

    known_item_ids = set(observations)
    items = [
        _history_item(
            item_id=item_id,
            observations=item_observations,
            comparison_versions=comparison_versions,
            publish_version=selected_publish_version,
            routes=routes,
            known_item_ids=known_item_ids,
        )
        for item_id, item_observations in observations.items()
    ]
    items = _attach_replacement_edges_to_both_endpoints(items)

    return SurfaceHistoryReport(
        surface_id=surface_id,
        title=title,
        format=ReferenceFormat.OPENRPC,
        configured_scope=configured_scope,
        history_mode=HistoryMode.SNAPSHOTS,
        publish_version=selected_publish_version,
        comparison_versions=comparison_versions,
        source_artifacts=tuple(
            SourceArtifact(
                version=source.version,
                source=source.source_path,
                revision=source.version,
                path=source.source_path,
            )
            for source in scoped_sources
        ),
        version_policy=VersionSelectionPolicy.CONFIGURED_PUBLISH_VERSION,
        items=tuple(sorted(items, key=lambda item: item.id)),
    )


def _history_item(
    *,
    item_id: str,
    observations: list[_MethodObservation],
    comparison_versions: tuple[str, ...],
    publish_version: str,
    routes: Mapping[tuple[str, str], str],
    known_item_ids: set[str],
) -> HistoryItem:
    first = observations[0]
    last = observations[-1]
    indexes = [comparison_versions.index(observation.version) for observation in observations]
    if any(right - left > 1 for left, right in zip(indexes, indexes[1:])):
        raise ValueError(f"OpenRPC method disappears and later reappears: {item_id}")

    current = next((item for item in observations if item.version == publish_version), None)
    current_present = current is not None
    route = routes.get((current.spec_id, current.detail["name"])) if current else None
    if current is not None and route is None:
        raise ValueError(f"Current OpenRPC method has no reader route: {item_id}")

    changes = _changes(observations)
    transitions = _lifecycle_transitions(observations)
    remove_as_of, remove_evidence = _remove_as_of(observations)
    replacement_edges = _replacement_edges(
        item_id=item_id,
        observations=observations,
        known_item_ids=known_item_ids,
    )

    observed_removal = None
    removal_evidence = None
    if not current_present:
        observed_removal = comparison_versions[comparison_versions.index(last.version) + 1]
        removal_evidence = Evidence(
            kind=EvidenceKind.SNAPSHOT_DIFF,
            source=last.source_path,
            observed_in_version=observed_removal,
            location=_location(last),
            detail="The method is absent from this OpenRPC snapshot.",
        )

    return HistoryItem(
        id=item_id,
        kind="openrpc_method",
        route=route,
        location=_location(current or last),
        first_seen=first.version,
        last_seen=last.version,
        current_present=current_present,
        introduction_evidence=Evidence(
            kind=EvidenceKind.SNAPSHOT,
            source=first.source_path,
            observed_in_version=first.version,
            location=_location(first),
        ),
        observed_removal=observed_removal,
        removal_evidence=removal_evidence,
        last_changed=changes[-1].version if changes else None,
        changes=changes,
        lifecycle_state=transitions[-1].state if transitions else None,
        lifecycle_transitions=transitions,
        remove_as_of=remove_as_of,
        remove_as_of_evidence=remove_evidence,
        replacement_edges=replacement_edges,
    )


def _changes(observations: list[_MethodObservation]) -> tuple[ChangeDetail, ...]:
    changes: list[ChangeDetail] = []
    previous = observations[0]
    for observation in observations[1:]:
        if observation.detail["fingerprint"] == previous.detail["fingerprint"]:
            previous = observation
            continue
        details = describe_method_changes(previous.detail, observation.detail)
        changes.append(
            ChangeDetail(
                version=observation.version,
                summary="; ".join(details) or "The method was updated in this snapshot.",
                evidence=(
                    Evidence(
                        kind=EvidenceKind.SNAPSHOT_DIFF,
                        source=observation.source_path,
                        observed_in_version=observation.version,
                        location=_location(observation),
                    ),
                ),
            )
        )
        previous = observation
    return tuple(changes)


def _lifecycle_transitions(observations: list[_MethodObservation]) -> tuple[LifecycleTransition, ...]:
    transitions: list[LifecycleTransition] = []
    previous_state: str | None = None
    for observation in observations:
        state = observation.detail.get("lifecycle_state")
        if state is None or state == previous_state:
            continue
        transitions.append(
            LifecycleTransition(
                state=LifecycleState(state),
                version=observation.version,
                evidence=Evidence(
                    kind=EvidenceKind.SOURCE_METADATA,
                    source=observation.source_path,
                    observed_in_version=observation.version,
                    location=_location(observation),
                    detail=f"x-state: {state}",
                ),
            )
        )
        previous_state = state
    return tuple(transitions)


def _remove_as_of(observations: list[_MethodObservation]) -> tuple[str | None, Evidence | None]:
    latest: _MethodObservation | None = None
    value: str | None = None
    for observation in observations:
        candidate = observation.detail.get("remove_as_of")
        if candidate == value:
            continue
        value = candidate
        latest = observation
    if value is None or latest is None:
        return None, None
    return value, Evidence(
        kind=EvidenceKind.SOURCE_METADATA,
        source=latest.source_path,
        observed_in_version=latest.version,
        location=_location(latest),
        detail=f"x-remove-as-of: {value}",
    )


def _replacement_edges(
    *,
    item_id: str,
    observations: list[_MethodObservation],
    known_item_ids: set[str],
) -> tuple[ReplacementEdge, ...]:
    edges: list[ReplacementEdge] = []
    seen: set[str] = set()
    for observation in observations:
        target = observation.detail.get("replaces")
        if target is None or target in seen:
            continue
        predecessor = target if "#" in target else openrpc_item_id(observation.spec_id, target)
        if predecessor not in known_item_ids:
            raise ValueError(f"OpenRPC x-replaces references unknown method: {predecessor}")
        seen.add(target)
        edges.append(
            ReplacementEdge(
                from_item_id=predecessor,
                to_item_id=item_id,
                version=observation.version,
                evidence=Evidence(
                    kind=EvidenceKind.SOURCE_METADATA,
                    source=observation.source_path,
                    observed_in_version=observation.version,
                    location=_location(observation),
                    detail=f"x-replaces: {target}",
                ),
            )
        )
    return tuple(edges)


def _attach_replacement_edges_to_both_endpoints(items: list[HistoryItem]) -> list[HistoryItem]:
    edges = {
        (edge.from_item_id, edge.to_item_id, edge.version): edge
        for item in items
        for edge in item.replacement_edges
    }
    by_item = {item.id: list(item.replacement_edges) for item in items}
    for edge in edges.values():
        for endpoint in (edge.from_item_id, edge.to_item_id):
            if edge not in by_item[endpoint]:
                by_item[endpoint].append(edge)
    return [replace(item, replacement_edges=tuple(by_item[item.id])) for item in items]


def _location(observation: _MethodObservation) -> str:
    return f"{observation.spec_id} {observation.detail['name']}"
