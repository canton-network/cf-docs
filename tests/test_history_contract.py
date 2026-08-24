from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from x2mdx.history import (
    EvidenceKind,
    HistoryEventKind,
    HistoryValidationError,
    IdentityConfidence,
    history_events_for_item,
    history_report_from_dict,
    history_report_to_dict,
    load_history_report,
    validate_history_report,
)


FIXTURE = Path(__file__).parent / "fixtures" / "history" / "conformance" / "report.json"


def conformance_report():
    return load_history_report(FIXTURE)


def test_three_version_conformance_report_is_valid() -> None:
    report = conformance_report()

    validate_history_report(report)

    assert report.comparison_versions == ("1.0.0", "1.1.0", "2.0.0")
    assert {item.id for item in report.current_items()} == {
        "payments.create",
        "payments.createV2",
    }


def test_history_events_are_newest_first_with_remove_as_of_at_the_top() -> None:
    report = conformance_report()
    item = report.items_by_id()["payments.create"]

    events = history_events_for_item(
        item, comparison_versions=report.comparison_versions
    )

    assert [event.kind for event in events] == [
        HistoryEventKind.REMOVE_AS_OF,
        HistoryEventKind.REPLACEMENT,
        HistoryEventKind.DEPRECATED,
        HistoryEventKind.CHANGED,
        HistoryEventKind.INTRODUCED,
    ]
    assert events[0].label == "Remove as of 2.1.0"


def test_current_item_at_removal_deadline_fails() -> None:
    report = conformance_report()
    item = report.items_by_id()["payments.create"]
    stale_item = replace(item, remove_as_of="2.0.0")
    stale_report = replace(
        report,
        items=tuple(
            stale_item if candidate.id == item.id else candidate
            for candidate in report.items
        ),
    )

    with pytest.raises(
        HistoryValidationError, match="still present at or after remove_as_of"
    ):
        validate_history_report(stale_report)


def test_item_removed_before_advertised_version_fails() -> None:
    report = conformance_report()
    item = report.items_by_id()["payments.legacy"]
    early_item = replace(item, remove_as_of="2.1.0")
    early_report = replace(
        report,
        items=tuple(
            early_item if candidate.id == item.id else candidate
            for candidate in report.items
        ),
    )

    with pytest.raises(HistoryValidationError, match="disappeared before remove_as_of"):
        validate_history_report(early_report)


def test_lifecycle_state_cannot_be_invented_from_snapshot_diff() -> None:
    report = conformance_report()
    item = report.items_by_id()["payments.create"]
    transition = item.lifecycle_transitions[0]
    invalid_evidence = replace(transition.evidence, kind=EvidenceKind.SNAPSHOT_DIFF)
    invalid_item = replace(
        item,
        lifecycle_transitions=(replace(transition, evidence=invalid_evidence),),
    )
    invalid_report = replace(
        report,
        items=tuple(
            invalid_item if candidate.id == item.id else candidate
            for candidate in report.items
        ),
    )

    with pytest.raises(
        HistoryValidationError, match="must use source_metadata or sidecar evidence"
    ):
        validate_history_report(invalid_report)


def test_fallback_identity_requires_evidence() -> None:
    report = conformance_report()
    item = report.items_by_id()["payments.create"]
    invalid_item = replace(
        item,
        identity_confidence=IdentityConfidence.FALLBACK,
        identity_evidence=(),
    )
    invalid_report = replace(
        report,
        items=tuple(
            invalid_item if candidate.id == item.id else candidate
            for candidate in report.items
        ),
    )

    with pytest.raises(HistoryValidationError, match="identity_evidence is required"):
        validate_history_report(invalid_report)


def test_report_round_trips_through_json_shape() -> None:
    report = conformance_report()
    payload = history_report_to_dict(report)

    round_tripped = history_report_from_dict(payload)

    assert round_tripped == report
    json.dumps(payload)
