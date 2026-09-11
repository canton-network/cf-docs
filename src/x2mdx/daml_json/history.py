from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from x2mdx.daml_json.lifecycle import extract_tagged_warning_messages
from x2mdx.daml_json.models import DamlDocsReport
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


@dataclass(frozen=True)
class DamlRemovalSchedule:
    version: str
    observed_in_version: str
    source: str
    detail: str | None = None


def load_daml_removal_schedules(path: Path) -> dict[str, DamlRemovalSchedule]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("modules"), dict):
        raise ValueError(f"{path} must contain a `modules` object")
    schedules: dict[str, DamlRemovalSchedule] = {}
    for module_name, raw_schedule in payload["modules"].items():
        if not isinstance(module_name, str) or not module_name:
            raise ValueError(f"{path} contains an invalid module name")
        if not isinstance(raw_schedule, dict):
            raise ValueError(f"{path} schedule for {module_name} must be an object")
        version = raw_schedule.get("remove_as_of")
        observed_in_version = raw_schedule.get("observed_in_version")
        source = raw_schedule.get("source")
        if not isinstance(version, str) or not version:
            raise ValueError(
                f"{path} schedule for {module_name} requires non-empty "
                "remove_as_of, observed_in_version, and source strings"
            )
        if not isinstance(observed_in_version, str) or not observed_in_version:
            raise ValueError(
                f"{path} schedule for {module_name} requires non-empty "
                "remove_as_of, observed_in_version, and source strings"
            )
        if not isinstance(source, str) or not source:
            raise ValueError(
                f"{path} schedule for {module_name} requires non-empty "
                "remove_as_of, observed_in_version, and source strings"
            )
        detail = raw_schedule.get("detail")
        if detail is not None and not isinstance(detail, str):
            raise ValueError(f"{path} detail for {module_name} must be a string")
        schedules[module_name] = DamlRemovalSchedule(
            version=version,
            observed_in_version=observed_in_version,
            source=source,
            detail=detail,
        )
    return schedules


def _snapshot_source(source_name: str, version: str) -> str:
    return f"{source_name} [{version}]"


def build_daml_surface_history_report(
    report: DamlDocsReport,
    *,
    routes: Mapping[str, str],
    surface_id: str,
    title: str,
    configured_scope: str,
    removal_schedules: Mapping[str, DamlRemovalSchedule] | None = None,
    excluded_modules: frozenset[str] = frozenset(),
) -> SurfaceHistoryReport:
    """Normalize module-level Daml docs JSON history into the shared contract."""
    comparison_versions = tuple(report.versions)
    if not comparison_versions:
        raise ValueError("Daml history requires at least one comparison version")

    schedules = removal_schedules or {}
    unknown_schedules = sorted(
        set(schedules) - (set(report.module_lifecycle) - set(excluded_modules))
    )
    if unknown_schedules:
        raise ValueError(
            "Removal schedules reference unknown Daml modules: "
            + ", ".join(unknown_schedules)
        )

    modules_by_name = {
        str(module.get("md_name", "")): module for module in report.modules
    }
    items: list[HistoryItem] = []
    for module_name, lifecycle in sorted(report.module_lifecycle.items()):
        if module_name in excluded_modules:
            continue
        first_seen = lifecycle.get("introduced_in")
        last_seen = lifecycle.get("last_seen_in")
        if first_seen is None or last_seen is None:
            raise ValueError(f"Incomplete Daml module lifecycle: {module_name}")

        current_present = lifecycle.get("status") == "active"
        route = routes.get(module_name) if current_present else None
        if current_present and route is None:
            raise ValueError(f"Current Daml module has no reader route: {module_name}")

        removed_in = lifecycle.get("removed_in")
        removal_evidence = None
        if removed_in is not None:
            removal_evidence = Evidence(
                kind=EvidenceKind.SNAPSHOT_DIFF,
                source=_snapshot_source(report.source_name, removed_in),
                observed_in_version=removed_in,
                location=module_name,
                detail="The module is absent from this Daml docs JSON snapshot.",
            )

        changes = tuple(
            ChangeDetail(
                version=version,
                summary="Module declarations or documentation updated.",
                evidence=(
                    Evidence(
                        kind=EvidenceKind.SNAPSHOT_DIFF,
                        source=_snapshot_source(report.source_name, version),
                        observed_in_version=version,
                        location=module_name,
                        detail="The normalized module docs differ from the preceding comparable snapshot.",
                    ),
                ),
            )
            for version in report.module_changes.get(module_name, ())
        )

        transitions: tuple[LifecycleTransition, ...] = ()
        lifecycle_state = None
        deprecation_version = report.module_deprecation_first_seen.get(module_name)
        module_doc = modules_by_name.get(module_name, {})
        deprecation_messages = extract_tagged_warning_messages(
            module_doc.get("md_warn"), "DeprecatedData"
        )
        if current_present and deprecation_version and deprecation_messages:
            transitions = (
                LifecycleTransition(
                    state=LifecycleState.DEPRECATED,
                    version=deprecation_version,
                    evidence=Evidence(
                        kind=EvidenceKind.SOURCE_METADATA,
                        source=_snapshot_source(report.source_name, deprecation_version),
                        observed_in_version=deprecation_version,
                        location=module_name,
                        detail=" ".join(deprecation_messages),
                    ),
                ),
            )
            lifecycle_state = LifecycleState.DEPRECATED

        schedule = schedules.get(module_name)
        schedule_evidence = None
        if schedule is not None:
            schedule_evidence = Evidence(
                kind=EvidenceKind.SIDECAR,
                source=schedule.source,
                observed_in_version=schedule.observed_in_version,
                location=module_name,
                detail=schedule.detail,
            )

        items.append(
            HistoryItem(
                id=module_name,
                kind="daml_module",
                route=route,
                location=module_name,
                first_seen=first_seen,
                last_seen=last_seen,
                current_present=current_present,
                introduction_evidence=Evidence(
                    kind=EvidenceKind.SNAPSHOT,
                    source=_snapshot_source(report.source_name, first_seen),
                    observed_in_version=first_seen,
                    location=module_name,
                ),
                observed_removal=removed_in,
                removal_evidence=removal_evidence,
                last_changed=changes[-1].version if changes else None,
                changes=changes,
                lifecycle_state=lifecycle_state,
                lifecycle_transitions=transitions,
                remove_as_of=schedule.version if schedule else None,
                remove_as_of_evidence=schedule_evidence,
            )
        )

    return SurfaceHistoryReport(
        surface_id=surface_id,
        title=title,
        format=ReferenceFormat.DAML_JSON,
        configured_scope=configured_scope,
        history_mode=HistoryMode.SNAPSHOTS,
        publish_version=report.publish_version,
        comparison_versions=comparison_versions,
        source_artifacts=tuple(
            SourceArtifact(
                version=version,
                source=_snapshot_source(report.source_name, version),
                revision=version,
            )
            for version in comparison_versions
        ),
        version_policy=VersionSelectionPolicy.LATEST_SELECTED_RELEASE,
        items=tuple(items),
        limitations=(
            "Daml docs JSON snapshots establish module additions, normalized module updates, authored module deprecations, and removals.",
            "Entity declarations remain anchored within their current module page; this report uses the reader page boundary as its item boundary.",
        ),
    )
