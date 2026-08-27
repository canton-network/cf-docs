from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

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


def _evidence(payload: dict[str, Any]) -> Evidence:
    return Evidence(
        kind=EvidenceKind(payload["kind"]),
        source=str(payload["source"]),
        observed_in_version=str(payload["observed_in_version"]),
        location=str(payload["location"])
        if payload.get("location") is not None
        else None,
        detail=str(payload["detail"]) if payload.get("detail") is not None else None,
    )


def _required_bool(payload: dict[str, Any], field: str) -> bool:
    value = payload[field]
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _item(payload: dict[str, Any]) -> HistoryItem:
    lifecycle_state_raw = payload.get("lifecycle_state")
    return HistoryItem(
        id=str(payload["id"]),
        kind=str(payload["kind"]),
        route=str(payload["route"]) if payload.get("route") is not None else None,
        location=str(payload["location"])
        if payload.get("location") is not None
        else None,
        first_seen=str(payload["first_seen"]),
        last_seen=str(payload["last_seen"]),
        current_present=_required_bool(payload, "current_present"),
        introduction_evidence=_evidence(payload["introduction_evidence"]),
        observed_removal=(
            str(payload["observed_removal"])
            if payload.get("observed_removal") is not None
            else None
        ),
        removal_evidence=(
            _evidence(payload["removal_evidence"])
            if payload.get("removal_evidence") is not None
            else None
        ),
        last_changed=str(payload["last_changed"])
        if payload.get("last_changed") is not None
        else None,
        changes=tuple(
            ChangeDetail(
                version=str(change["version"]),
                summary=str(change["summary"]),
                evidence=tuple(_evidence(evidence) for evidence in change["evidence"]),
            )
            for change in payload.get("changes", [])
        ),
        lifecycle_state=LifecycleState(lifecycle_state_raw)
        if lifecycle_state_raw is not None
        else None,
        lifecycle_transitions=tuple(
            LifecycleTransition(
                state=LifecycleState(transition["state"]),
                version=str(transition["version"]),
                evidence=_evidence(transition["evidence"]),
            )
            for transition in payload.get("lifecycle_transitions", [])
        ),
        remove_as_of=str(payload["remove_as_of"])
        if payload.get("remove_as_of") is not None
        else None,
        remove_as_of_evidence=(
            _evidence(payload["remove_as_of_evidence"])
            if payload.get("remove_as_of_evidence") is not None
            else None
        ),
        replacement_edges=tuple(
            ReplacementEdge(
                from_item_id=str(edge["from_item_id"]),
                to_item_id=str(edge["to_item_id"]),
                version=str(edge["version"]),
                evidence=_evidence(edge["evidence"]),
            )
            for edge in payload.get("replacement_edges", [])
        ),
        identity_confidence=IdentityConfidence(
            payload.get("identity_confidence", "exact")
        ),
        identity_evidence=tuple(
            _evidence(evidence) for evidence in payload.get("identity_evidence", [])
        ),
    )


def history_report_from_dict(payload: dict[str, Any]) -> SurfaceHistoryReport:
    return SurfaceHistoryReport(
        surface_id=str(payload["surface_id"]),
        title=str(payload["title"]),
        format=ReferenceFormat(payload["format"]),
        configured_scope=str(payload["configured_scope"]),
        history_mode=HistoryMode(payload["history_mode"]),
        publish_version=str(payload["publish_version"]),
        comparison_versions=tuple(
            str(version) for version in payload["comparison_versions"]
        ),
        source_artifacts=tuple(
            SourceArtifact(
                version=str(source["version"]),
                source=str(source["source"]),
                revision=str(source["revision"])
                if source.get("revision") is not None
                else None,
                path=str(source["path"]) if source.get("path") is not None else None,
            )
            for source in payload.get("source_artifacts", [])
        ),
        version_policy=VersionSelectionPolicy(payload["version_policy"]),
        items=tuple(_item(item) for item in payload.get("items", [])),
        limitations=tuple(
            str(limitation) for limitation in payload.get("limitations", [])
        ),
    )


def load_history_report(path: Path) -> SurfaceHistoryReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"History report must be a JSON object: {path}")
    return history_report_from_dict(payload)


def history_report_to_dict(report: SurfaceHistoryReport) -> dict[str, Any]:
    return asdict(report)


def write_history_report(path: Path, report: SurfaceHistoryReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(history_report_to_dict(report), indent=2) + "\n",
        encoding="utf-8",
    )
