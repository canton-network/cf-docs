from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from x2mdx.history.models import (
    ChangeDetail,
    Evidence,
    EvidenceKind,
    HistoryItem,
    HistoryMode,
    LifecycleState,
    LifecycleTransition,
    ReferenceFormat,
    SourceArtifact,
    SurfaceHistoryReport,
    VersionSelectionPolicy,
)
from x2mdx.typedoc.models import TypeDocReport


@dataclass(frozen=True)
class TypeDocRemovalSchedule:
    version: str
    observed_in_version: str
    source: str
    detail: str | None = None


def typedoc_item_id(package_name: str, export_key: str) -> str:
    return f"{package_name}::{export_key}"


def load_typedoc_removal_schedules(path: Path) -> dict[str, TypeDocRemovalSchedule]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("exports"), dict):
        raise ValueError(f"{path} must contain an `exports` object")
    schedules: dict[str, TypeDocRemovalSchedule] = {}
    for item_id, raw_schedule in payload["exports"].items():
        if not isinstance(item_id, str) or not item_id:
            raise ValueError(f"{path} contains an invalid TypeDoc export ID")
        if not isinstance(raw_schedule, dict):
            raise ValueError(f"{path} schedule for {item_id} must be an object")
        version = raw_schedule.get("remove_as_of")
        observed_in_version = raw_schedule.get("observed_in_version")
        source = raw_schedule.get("source")
        if not isinstance(version, str) or not version:
            raise ValueError(
                f"{path} schedule for {item_id} requires non-empty remove_as_of, "
                "observed_in_version, and source strings"
            )
        if not isinstance(observed_in_version, str) or not observed_in_version:
            raise ValueError(
                f"{path} schedule for {item_id} requires non-empty remove_as_of, "
                "observed_in_version, and source strings"
            )
        if not isinstance(source, str) or not source:
            raise ValueError(
                f"{path} schedule for {item_id} requires non-empty remove_as_of, "
                "observed_in_version, and source strings"
            )
        detail = raw_schedule.get("detail")
        if detail is not None and not isinstance(detail, str):
            raise ValueError(f"{path} detail for {item_id} must be a string")
        schedules[item_id] = TypeDocRemovalSchedule(
            version=version,
            observed_in_version=observed_in_version,
            source=source,
            detail=detail,
        )
    return schedules


def _snapshot_source(report: TypeDocReport, version: str) -> str:
    return f"{report.source_name} [{version}]"


def build_typedoc_surface_history_report(
    report: TypeDocReport,
    *,
    reader_route: str,
    surface_id: str,
    title: str,
    configured_scope: str,
    removal_schedules: Mapping[str, TypeDocRemovalSchedule] | None = None,
) -> SurfaceHistoryReport:
    comparison_versions = tuple(report.versions)
    if not comparison_versions:
        raise ValueError("TypeDoc history requires at least one comparison version")

    schedules = removal_schedules or {}
    known_item_ids = {
        typedoc_item_id(report.package_name, str(cast(dict[str, Any], export)["key"]))
        for export in report.exports
    }
    package_prefix = f"{report.package_name}::"
    package_schedules = {
        item_id: schedule
        for item_id, schedule in schedules.items()
        if item_id.startswith(package_prefix)
    }
    unknown_schedules = sorted(set(package_schedules) - known_item_ids)
    if unknown_schedules:
        raise ValueError(
            "Removal schedules reference unknown TypeDoc exports: "
            + ", ".join(unknown_schedules)
        )

    items: list[HistoryItem] = []
    for raw_export in report.exports:
        export = cast(dict[str, Any], raw_export)
        item_id = typedoc_item_id(report.package_name, str(export["key"]))
        current_present = export["status"] == "active"
        route = f"{reader_route}#{export['anchor']}" if current_present else None
        removed_in = export.get("removed_in")
        location = str(export.get("source_location") or export["key"])
        changes = tuple(
            ChangeDetail(
                version=str(change["version"]),
                summary="; ".join(str(detail) for detail in change.get("changes", []))
                or "The exported symbol was updated in this snapshot.",
                evidence=(
                    Evidence(
                        kind=EvidenceKind.SNAPSHOT_DIFF,
                        source=_snapshot_source(report, str(change["version"])),
                        observed_in_version=str(change["version"]),
                        location=location,
                    ),
                ),
            )
            for change in export.get("change_details", [])
        )
        transitions = tuple(
            LifecycleTransition(
                state=LifecycleState(str(transition["state"])),
                version=str(transition["version"]),
                evidence=Evidence(
                    kind=EvidenceKind.SOURCE_METADATA,
                    source=_snapshot_source(report, str(transition["version"])),
                    observed_in_version=str(transition["version"]),
                    location=str(transition["location"]),
                    detail=str(transition["detail"]),
                ),
            )
            for transition in export.get("lifecycle_transitions", [])
        )
        schedule = package_schedules.get(item_id)
        items.append(
            HistoryItem(
                id=item_id,
                kind="typedoc_package_symbol",
                route=route,
                location=location,
                first_seen=str(export["introduced_in"]),
                last_seen=str(export["last_seen_in"]),
                current_present=current_present,
                introduction_evidence=Evidence(
                    kind=EvidenceKind.SNAPSHOT,
                    source=_snapshot_source(report, str(export["introduced_in"])),
                    observed_in_version=str(export["introduced_in"]),
                    location=location,
                ),
                observed_removal=str(removed_in) if removed_in is not None else None,
                removal_evidence=(
                    Evidence(
                        kind=EvidenceKind.SNAPSHOT_DIFF,
                        source=_snapshot_source(report, str(removed_in)),
                        observed_in_version=str(removed_in),
                        location=location,
                        detail="The exported symbol is absent from this TypeDoc snapshot.",
                    )
                    if removed_in is not None
                    else None
                ),
                last_changed=changes[-1].version if changes else None,
                changes=changes,
                lifecycle_state=transitions[-1].state if transitions else None,
                lifecycle_transitions=transitions,
                remove_as_of=schedule.version if schedule else None,
                remove_as_of_evidence=(
                    Evidence(
                        kind=EvidenceKind.SIDECAR,
                        source=schedule.source,
                        observed_in_version=schedule.observed_in_version,
                        location=item_id,
                        detail=schedule.detail,
                    )
                    if schedule
                    else None
                ),
            )
        )

    return SurfaceHistoryReport(
        surface_id=surface_id,
        title=title,
        format=ReferenceFormat.TYPEDOC,
        configured_scope=configured_scope,
        history_mode=HistoryMode.SNAPSHOTS,
        publish_version=report.publish_version,
        comparison_versions=comparison_versions,
        source_artifacts=tuple(
            SourceArtifact(
                version=version,
                source=_snapshot_source(report, version),
                revision=version,
            )
            for version in comparison_versions
        ),
        version_policy=VersionSelectionPolicy.LATEST_SELECTED_RELEASE,
        items=tuple(items),
        limitations=(
            "TypeDoc snapshots establish exported-symbol additions, normalized updates, authored lifecycle states, and removals.",
            "Current symbols are anchored within one package reader page; removed symbols remain report-only.",
        ),
    )
