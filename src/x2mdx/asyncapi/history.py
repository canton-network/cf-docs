from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from x2mdx.asyncapi.lifecycle import (
    collect_snapshot_channels,
    describe_action_changes,
    sha256_json,
    version_key,
)
from x2mdx.asyncapi.models import (
    AsyncApiActionDetail,
    AsyncApiChannelDetail,
    AsyncApiSourceSnapshot,
)
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


@dataclass(frozen=True)
class _ActionObservation:
    version: str
    channel: str
    channel_detail: AsyncApiChannelDetail
    action: AsyncApiActionDetail
    fingerprint: str


def asyncapi_item_id(channel: str, action: str) -> str:
    return f"{channel}#{action}"


def build_asyncapi_history_report(
    *,
    sources: list[AsyncApiSourceSnapshot],
    routes: Mapping[tuple[str, str], str],
    publish_version: str | None = None,
    surface_id: str = "json-ledger-api-asyncapi",
    title: str = "JSON Ledger API AsyncAPI",
    configured_scope: str = "JSON Ledger API WebSocket channel actions",
) -> SurfaceHistoryReport:
    if not sources:
        raise ValueError("AsyncAPI history requires at least one snapshot")

    ordered_sources = sorted(sources, key=lambda snapshot: version_key(snapshot.version))
    ordered_versions = tuple(snapshot.version for snapshot in ordered_sources)
    selected_publish_version = publish_version or ordered_versions[-1]
    if selected_publish_version not in ordered_versions:
        raise ValueError(
            f"Publish version '{selected_publish_version}' is not present in selected snapshots: "
            f"{list(ordered_versions)}"
        )
    publish_index = ordered_versions.index(selected_publish_version)
    scoped_sources = ordered_sources[: publish_index + 1]
    comparison_versions = tuple(snapshot.version for snapshot in scoped_sources)
    sources_by_version = {
        snapshot.version: snapshot.source_url or snapshot.source_path
        for snapshot in scoped_sources
    }

    observations: dict[str, list[_ActionObservation]] = {}
    for snapshot in scoped_sources:
        for channel, channel_detail in collect_snapshot_channels(snapshot.document).items():
            for action in channel_detail["actions"]:
                item_id = asyncapi_item_id(channel, action["action"])
                observations.setdefault(item_id, []).append(
                    _ActionObservation(
                        version=snapshot.version,
                        channel=channel,
                        channel_detail=channel_detail,
                        action=action,
                        fingerprint=_action_fingerprint(channel_detail, action),
                    )
                )

    known_item_ids = set(observations)
    items = [
        _history_item(
            item_id=item_id,
            observations=item_observations,
            comparison_versions=comparison_versions,
            publish_version=selected_publish_version,
            sources_by_version=sources_by_version,
            routes=routes,
            known_item_ids=known_item_ids,
        )
        for item_id, item_observations in observations.items()
    ]
    items = _attach_replacement_edges_to_both_endpoints(items)

    return SurfaceHistoryReport(
        surface_id=surface_id,
        title=title,
        format=ReferenceFormat.ASYNCAPI,
        configured_scope=configured_scope,
        history_mode=HistoryMode.SNAPSHOTS,
        publish_version=selected_publish_version,
        comparison_versions=comparison_versions,
        source_artifacts=tuple(
            SourceArtifact(
                version=snapshot.version,
                source=snapshot.source_url or snapshot.source_path,
                revision=snapshot.version,
                path=snapshot.source_path,
            )
            for snapshot in scoped_sources
        ),
        version_policy=VersionSelectionPolicy.CONFIGURED_PUBLISH_VERSION,
        items=tuple(sorted(items, key=lambda item: item.id)),
    )


def _action_fingerprint(
    channel_detail: AsyncApiChannelDetail,
    action: AsyncApiActionDetail,
) -> str:
    action_contract = {
        key: value
        for key, value in action.items()
        if key not in {"lifecycle_state", "replaces", "remove_as_of"}
    }
    return sha256_json(
        {
            "channel_description": channel_detail["description"],
            "action": action_contract,
        }
    )


def _history_item(
    *,
    item_id: str,
    observations: list[_ActionObservation],
    comparison_versions: tuple[str, ...],
    publish_version: str,
    sources_by_version: Mapping[str, str],
    routes: Mapping[tuple[str, str], str],
    known_item_ids: set[str],
) -> HistoryItem:
    first = observations[0]
    last = observations[-1]
    observation_indexes = [
        comparison_versions.index(observation.version) for observation in observations
    ]
    if any(
        right - left > 1
        for left, right in zip(observation_indexes, observation_indexes[1:])
    ):
        raise ValueError(
            f"AsyncAPI channel action disappears and later reappears: {item_id}"
        )

    current = next(
        (
            observation
            for observation in observations
            if observation.version == publish_version
        ),
        None,
    )
    current_present = current is not None
    location_observation = current or last
    route = None
    if current is not None:
        route = routes.get((current.channel, current.action["action"]))
        if route is None:
            raise ValueError(f"Current AsyncAPI action has no reader route: {item_id}")

    changes = _changes(observations, sources_by_version=sources_by_version)
    lifecycle_transitions = _lifecycle_transitions(
        observations,
        sources_by_version=sources_by_version,
    )
    remove_as_of, remove_as_of_evidence = _remove_as_of(
        observations,
        sources_by_version=sources_by_version,
    )
    replacement_edges = _replacement_edges(
        item_id=item_id,
        observations=observations,
        sources_by_version=sources_by_version,
        known_item_ids=known_item_ids,
    )

    observed_removal = None
    removal_evidence = None
    if not current_present:
        last_index = comparison_versions.index(last.version)
        observed_removal = comparison_versions[last_index + 1]
        removal_evidence = Evidence(
            kind=EvidenceKind.SNAPSHOT_DIFF,
            source=sources_by_version[observed_removal],
            observed_in_version=observed_removal,
            location=_location(last),
            detail="The channel action is absent from this AsyncAPI snapshot.",
        )

    return HistoryItem(
        id=item_id,
        kind="channel_action",
        route=route,
        location=_location(location_observation),
        first_seen=first.version,
        last_seen=last.version,
        current_present=current_present,
        introduction_evidence=Evidence(
            kind=EvidenceKind.SNAPSHOT,
            source=sources_by_version[first.version],
            observed_in_version=first.version,
            location=_location(first),
        ),
        observed_removal=observed_removal,
        removal_evidence=removal_evidence,
        last_changed=changes[-1].version if changes else None,
        changes=changes,
        lifecycle_state=(
            lifecycle_transitions[-1].state if lifecycle_transitions else None
        ),
        lifecycle_transitions=lifecycle_transitions,
        remove_as_of=remove_as_of,
        remove_as_of_evidence=remove_as_of_evidence,
        replacement_edges=replacement_edges,
    )


def _changes(
    observations: list[_ActionObservation],
    *,
    sources_by_version: Mapping[str, str],
) -> tuple[ChangeDetail, ...]:
    changes: list[ChangeDetail] = []
    previous = observations[0]
    for observation in observations[1:]:
        if observation.fingerprint == previous.fingerprint:
            previous = observation
            continue
        details = describe_action_changes(
            previous.action,
            observation.action,
            action_name=observation.action["action"],
        )
        if previous.channel_detail["description"] != observation.channel_detail["description"]:
            details.insert(0, "channel description updated")
        summary = "; ".join(details) or "The channel action was updated in this snapshot."
        changes.append(
            ChangeDetail(
                version=observation.version,
                summary=summary,
                evidence=(
                    Evidence(
                        kind=EvidenceKind.SNAPSHOT_DIFF,
                        source=sources_by_version[observation.version],
                        observed_in_version=observation.version,
                        location=_location(observation),
                    ),
                ),
            )
        )
        previous = observation
    return tuple(changes)


def _lifecycle_transitions(
    observations: list[_ActionObservation],
    *,
    sources_by_version: Mapping[str, str],
) -> tuple[LifecycleTransition, ...]:
    transitions: list[LifecycleTransition] = []
    previous_state: str | None = None
    for observation in observations:
        state = _effective_authored_value(observation, "lifecycle_state")
        if state is None:
            continue
        if state == previous_state:
            continue
        transitions.append(
            LifecycleTransition(
                state=LifecycleState(state),
                version=observation.version,
                evidence=Evidence(
                    kind=EvidenceKind.SOURCE_METADATA,
                    source=sources_by_version[observation.version],
                    observed_in_version=observation.version,
                    location=_location(observation),
                    detail=f"x-state: {state}",
                ),
            )
        )
        previous_state = state
    return tuple(transitions)


def _remove_as_of(
    observations: list[_ActionObservation],
    *,
    sources_by_version: Mapping[str, str],
) -> tuple[str | None, Evidence | None]:
    latest_value: str | None = None
    latest_observation: _ActionObservation | None = None
    for observation in observations:
        value = _effective_authored_value(observation, "remove_as_of")
        if value == latest_value:
            continue
        latest_value = value
        latest_observation = observation
    if latest_value is None or latest_observation is None:
        return None, None
    return latest_value, Evidence(
        kind=EvidenceKind.SOURCE_METADATA,
        source=sources_by_version[latest_observation.version],
        observed_in_version=latest_observation.version,
        location=_location(latest_observation),
        detail=f"x-remove-as-of: {latest_value}",
    )


def _replacement_edges(
    *,
    item_id: str,
    observations: list[_ActionObservation],
    sources_by_version: Mapping[str, str],
    known_item_ids: set[str],
) -> tuple[ReplacementEdge, ...]:
    edges: list[ReplacementEdge] = []
    seen_predecessors: set[str] = set()
    for observation in observations:
        value = _effective_authored_value(observation, "replaces")
        if value is None:
            continue
        predecessor_id = _replacement_item_id(observation, value)
        if predecessor_id in seen_predecessors:
            continue
        if predecessor_id not in known_item_ids:
            raise ValueError(
                f"AsyncAPI x-replaces references unknown channel action: {predecessor_id}"
            )
        seen_predecessors.add(predecessor_id)
        edges.append(
            ReplacementEdge(
                from_item_id=predecessor_id,
                to_item_id=item_id,
                version=observation.version,
                evidence=Evidence(
                    kind=EvidenceKind.SOURCE_METADATA,
                    source=sources_by_version[observation.version],
                    observed_in_version=observation.version,
                    location=_location(observation),
                    detail=f"x-replaces: {value}",
                ),
            )
        )
    return tuple(edges)


def _replacement_item_id(
    observation: _ActionObservation,
    authored_value: str,
) -> str:
    if "#" in authored_value:
        return authored_value
    return asyncapi_item_id(authored_value, observation.action["action"])


def _effective_authored_value(
    observation: _ActionObservation,
    field: str,
) -> str | None:
    action_value = observation.action.get(field)
    if isinstance(action_value, str) and action_value:
        return action_value
    channel_value = observation.channel_detail.get(field)
    if isinstance(channel_value, str) and channel_value:
        return channel_value
    return None


def _location(observation: _ActionObservation) -> str:
    return f"{observation.channel} {observation.action['action']}"


def _attach_replacement_edges_to_both_endpoints(
    items: list[HistoryItem],
) -> list[HistoryItem]:
    edges = {
        (edge.from_item_id, edge.to_item_id, edge.version): edge
        for item in items
        for edge in item.replacement_edges
    }
    edges_by_item_id: dict[str, list[ReplacementEdge]] = {
        item.id: list(item.replacement_edges) for item in items
    }
    for edge in edges.values():
        for endpoint in (edge.from_item_id, edge.to_item_id):
            if edge not in edges_by_item_id[endpoint]:
                edges_by_item_id[endpoint].append(edge)
    return [
        replace(item, replacement_edges=tuple(edges_by_item_id[item.id]))
        for item in items
    ]
