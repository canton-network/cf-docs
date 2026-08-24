from __future__ import annotations

from functools import cmp_to_key

from x2mdx.history.models import (
    HistoryEvent,
    HistoryEventKind,
    HistoryItem,
    LifecycleState,
)
from x2mdx.history.versioning import compare_versions


EVENT_KIND_PRIORITY = {
    HistoryEventKind.REMOVE_AS_OF: 0,
    HistoryEventKind.DEPRECATED: 1,
    HistoryEventKind.CHANGED: 2,
    HistoryEventKind.INTRODUCED: 3,
    HistoryEventKind.REPLACEMENT: 4,
}


def history_events_for_item(
    item: HistoryItem,
    *,
    comparison_versions: tuple[str, ...],
) -> tuple[HistoryEvent, ...]:
    events: list[HistoryEvent] = []
    if item.remove_as_of is not None and item.remove_as_of_evidence is not None:
        events.append(
            HistoryEvent(
                kind=HistoryEventKind.REMOVE_AS_OF,
                version=item.remove_as_of,
                label="Remove as of",
                details=(),
                evidence=(item.remove_as_of_evidence,),
            )
        )

    for transition in item.lifecycle_transitions:
        if transition.state != LifecycleState.DEPRECATED:
            continue
        events.append(
            HistoryEvent(
                kind=HistoryEventKind.DEPRECATED,
                version=transition.version,
                label="Deprecated",
                details=(),
                evidence=(transition.evidence,),
            )
        )

    for change in item.changes:
        events.append(
            HistoryEvent(
                kind=HistoryEventKind.CHANGED,
                version=change.version,
                label="Changed",
                details=(change.summary,),
                evidence=change.evidence,
            )
        )

    events.append(
        HistoryEvent(
            kind=HistoryEventKind.INTRODUCED,
            version=item.first_seen,
            label="Introduced",
            details=(),
            evidence=(item.introduction_evidence,),
        )
    )

    for edge in item.replacement_edges:
        if edge.to_item_id == item.id:
            detail = f"Replaces {edge.from_item_id}"
        else:
            detail = f"Replaced by {edge.to_item_id}"
        events.append(
            HistoryEvent(
                kind=HistoryEventKind.REPLACEMENT,
                version=edge.version,
                label="Replacement",
                details=(detail,),
                evidence=(edge.evidence,),
            )
        )

    def compare_events(left: HistoryEvent, right: HistoryEvent) -> int:
        version_comparison = compare_versions(
            left.version,
            right.version,
            known_order=comparison_versions,
        )
        if version_comparison:
            return -version_comparison
        return EVENT_KIND_PRIORITY[left.kind] - EVENT_KIND_PRIORITY[right.kind]

    return tuple(sorted(events, key=cmp_to_key(compare_events)))
