from __future__ import annotations

from x2mdx.history.models import (
    Evidence,
    EvidenceKind,
    HistoryItem,
    HistoryMode,
    IdentityConfidence,
    SurfaceHistoryReport,
)
from x2mdx.history.versioning import compare_versions


AUTHORED_EVIDENCE_KINDS = {EvidenceKind.SOURCE_METADATA, EvidenceKind.SIDECAR}
CHANGE_EVIDENCE_KINDS = {EvidenceKind.SNAPSHOT_DIFF, *AUTHORED_EVIDENCE_KINDS}


class HistoryValidationError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("Invalid history report:\n- " + "\n- ".join(problems))


def _require_authored_evidence(
    evidence: Evidence, *, field: str, item: HistoryItem, problems: list[str]
) -> None:
    if evidence.kind not in AUTHORED_EVIDENCE_KINDS:
        problems.append(
            f"{item.id}.{field} must use source_metadata or sidecar evidence, got {evidence.kind.value}"
        )


def _validate_evidence(
    evidence: Evidence,
    *,
    field: str,
    item: HistoryItem,
    report: SurfaceHistoryReport,
    problems: list[str],
) -> None:
    if not evidence.source.strip():
        problems.append(f"{item.id}.{field}.source must not be empty")
    if evidence.observed_in_version not in report.comparison_versions:
        problems.append(
            f"{item.id}.{field}.observed_in_version is outside comparison_versions: "
            f"{evidence.observed_in_version}"
        )


def _validate_item(
    item: HistoryItem,
    *,
    report: SurfaceHistoryReport,
    item_ids: set[str],
    problems: list[str],
) -> None:
    versions = report.comparison_versions
    for field, version in (
        ("first_seen", item.first_seen),
        ("last_seen", item.last_seen),
    ):
        if version not in versions:
            problems.append(
                f"{item.id}.{field} is outside comparison_versions: {version}"
            )
    if compare_versions(item.first_seen, item.last_seen, known_order=versions) > 0:
        problems.append(f"{item.id}.first_seen must not be after last_seen")

    if item.introduction_evidence.kind != EvidenceKind.SNAPSHOT:
        problems.append(f"{item.id}.introduction_evidence must use snapshot evidence")
    if item.introduction_evidence.observed_in_version != item.first_seen:
        problems.append(
            f"{item.id}.introduction_evidence must be observed in first_seen"
        )
    _validate_evidence(
        item.introduction_evidence,
        field="introduction_evidence",
        item=item,
        report=report,
        problems=problems,
    )
    if item.current_present:
        if not item.route:
            problems.append(f"{item.id}.route is required for a current item")
        if item.last_seen != report.publish_version:
            problems.append(
                f"{item.id}.last_seen must equal publish_version while current"
            )
        if item.observed_removal is not None or item.removal_evidence is not None:
            problems.append(
                f"{item.id} is current and cannot have observed removal evidence"
            )
    else:
        if item.observed_removal is None or item.removal_evidence is None:
            problems.append(
                f"{item.id} is absent from the publish snapshot and requires observed removal evidence"
            )
        else:
            if item.observed_removal not in versions:
                problems.append(
                    f"{item.id}.observed_removal is outside comparison_versions"
                )
            if (
                compare_versions(
                    item.last_seen, item.observed_removal, known_order=versions
                )
                >= 0
            ):
                problems.append(f"{item.id}.observed_removal must be after last_seen")
            if item.removal_evidence.kind != EvidenceKind.SNAPSHOT_DIFF:
                problems.append(
                    f"{item.id}.removal_evidence must use snapshot_diff evidence"
                )
            if item.removal_evidence.observed_in_version != item.observed_removal:
                problems.append(
                    f"{item.id}.removal_evidence must be observed in observed_removal"
                )
            _validate_evidence(
                item.removal_evidence,
                field="removal_evidence",
                item=item,
                report=report,
                problems=problems,
            )

    change_versions = [change.version for change in item.changes]
    if len(change_versions) != len(set(change_versions)):
        problems.append(f"{item.id}.changes contains duplicate versions")
    for change in item.changes:
        if change.version not in versions:
            problems.append(
                f"{item.id}.changes contains a version outside comparison_versions: {change.version}"
            )
        if not change.summary.strip():
            problems.append(f"{item.id}.changes contains an empty summary")
        if not change.evidence:
            problems.append(f"{item.id}.changes[{change.version}] requires evidence")
        for evidence in change.evidence:
            if evidence.kind not in CHANGE_EVIDENCE_KINDS:
                problems.append(
                    f"{item.id}.changes[{change.version}] cannot use {evidence.kind.value} evidence"
                )
            _validate_evidence(
                evidence,
                field=f"changes[{change.version}].evidence",
                item=item,
                report=report,
                problems=problems,
            )
    expected_last_changed = None
    for version in versions:
        if version in change_versions:
            expected_last_changed = version
    if item.last_changed != expected_last_changed:
        problems.append(
            f"{item.id}.last_changed must match the newest change version: {expected_last_changed}"
        )

    for transition in item.lifecycle_transitions:
        if transition.version not in versions:
            problems.append(
                f"{item.id}.lifecycle_transitions[{transition.state.value}] is outside comparison_versions"
            )
        _require_authored_evidence(
            transition.evidence,
            field=f"lifecycle_transitions[{transition.state.value}]",
            item=item,
            problems=problems,
        )
        _validate_evidence(
            transition.evidence,
            field=f"lifecycle_transitions[{transition.state.value}].evidence",
            item=item,
            report=report,
            problems=problems,
        )
    if item.lifecycle_transitions:
        latest_transition = item.lifecycle_transitions[0]
        for transition in item.lifecycle_transitions[1:]:
            if (
                compare_versions(
                    transition.version,
                    latest_transition.version,
                    known_order=versions,
                )
                > 0
            ):
                latest_transition = transition
        if item.lifecycle_state != latest_transition.state:
            problems.append(
                f"{item.id}.lifecycle_state must match its latest authored transition"
            )
    elif item.lifecycle_state is not None:
        problems.append(f"{item.id}.lifecycle_state requires an authored transition")

    if (item.remove_as_of is None) != (item.remove_as_of_evidence is None):
        problems.append(
            f"{item.id}.remove_as_of and remove_as_of_evidence must be supplied together"
        )
    if item.remove_as_of is not None and item.remove_as_of_evidence is not None:
        _require_authored_evidence(
            item.remove_as_of_evidence,
            field="remove_as_of_evidence",
            item=item,
            problems=problems,
        )
        _validate_evidence(
            item.remove_as_of_evidence,
            field="remove_as_of_evidence",
            item=item,
            report=report,
            problems=problems,
        )
        if item.current_present:
            if (
                compare_versions(
                    report.publish_version,
                    item.remove_as_of,
                    known_order=versions,
                )
                >= 0
            ):
                problems.append(
                    f"{item.id} is still present at or after remove_as_of {item.remove_as_of}"
                )
        elif item.observed_removal is not None:
            removal_comparison = compare_versions(
                item.observed_removal,
                item.remove_as_of,
                known_order=versions,
            )
            if removal_comparison < 0:
                problems.append(
                    f"{item.id} disappeared before remove_as_of {item.remove_as_of}"
                )
            elif removal_comparison > 0:
                problems.append(
                    f"{item.id} remained present after remove_as_of {item.remove_as_of}"
                )

    for edge in item.replacement_edges:
        if edge.version not in versions:
            problems.append(
                f"{item.id}.replacement_edges version is outside comparison_versions: {edge.version}"
            )
        if edge.from_item_id == edge.to_item_id:
            problems.append(
                f"{item.id}.replacement_edges cannot replace an item with itself"
            )
        for endpoint in edge.from_item_id, edge.to_item_id:
            if endpoint not in item_ids:
                problems.append(
                    f"{item.id}.replacement_edges references unknown item: {endpoint}"
                )
        _require_authored_evidence(
            edge.evidence,
            field="replacement_edges",
            item=item,
            problems=problems,
        )
        _validate_evidence(
            edge.evidence,
            field="replacement_edges.evidence",
            item=item,
            report=report,
            problems=problems,
        )

    if (
        item.identity_confidence == IdentityConfidence.FALLBACK
        and not item.identity_evidence
    ):
        problems.append(
            f"{item.id}.identity_evidence is required for fallback identity"
        )
    for evidence in item.identity_evidence:
        _validate_evidence(
            evidence,
            field="identity_evidence",
            item=item,
            report=report,
            problems=problems,
        )


def validate_history_report(report: SurfaceHistoryReport) -> None:
    problems: list[str] = []
    versions = report.comparison_versions
    if not versions:
        problems.append("comparison_versions must not be empty")
    if len(versions) != len(set(versions)):
        problems.append("comparison_versions must be unique")
    if report.publish_version not in versions:
        problems.append("publish_version must be present in comparison_versions")
    if report.history_mode == HistoryMode.UNAVAILABLE and not report.limitations:
        problems.append("history_mode=unavailable requires at least one limitation")

    source_versions = {source.version for source in report.source_artifacts}
    if report.history_mode == HistoryMode.SNAPSHOTS:
        missing_source_versions = [
            version for version in versions if version not in source_versions
        ]
        if missing_source_versions:
            problems.append(
                "snapshot history requires source artifacts for every comparison version: "
                + ", ".join(missing_source_versions)
            )

    item_ids = [item.id for item in report.items]
    if len(item_ids) != len(set(item_ids)):
        problems.append("item IDs must be unique")
    known_item_ids = set(item_ids)
    for item in report.items:
        _validate_item(item, report=report, item_ids=known_item_ids, problems=problems)

    if problems:
        raise HistoryValidationError(problems)
