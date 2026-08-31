from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from x2mdx.history.models import (
    ChangeDetail,
    Evidence,
    EvidenceKind,
    HistoryItem,
    HistoryMode,
    ReferenceFormat,
    SourceArtifact,
    SurfaceHistoryReport,
    VersionSelectionPolicy,
)


def build_protobuf_surface_history_report(
    report: dict[str, Any],
    *,
    routes: Mapping[str, str],
    surface_id: str,
    title: str,
    configured_scope: str,
    format: ReferenceFormat = ReferenceFormat.PROTOBUF,
) -> SurfaceHistoryReport:
    """Normalize descriptor snapshot deltas into the shared history contract."""
    releases = list(report["releases"])
    if not releases:
        raise ValueError("Protobuf history requires at least one release")

    comparison_versions = tuple(str(release["version"]) for release in releases)
    publish_version = comparison_versions[-1]
    endpoint_versions: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    modified_by_id: dict[str, list[tuple[str, list[str], dict[str, Any]]]] = {}

    for release in releases:
        version = str(release["version"])
        for endpoint_id, endpoint in release["snapshot"]["endpoints"].items():
            endpoint_versions.setdefault(str(endpoint_id), []).append(
                (version, endpoint)
            )
        for change in release["changes"]["endpoints"]["modified"]:
            modified_by_id.setdefault(str(change["id"]), []).append(
                (version, list(change.get("changeTypes") or []), change["current"])
            )

    latest_endpoint_ids = set(releases[-1]["snapshot"]["endpoints"])
    items: list[HistoryItem] = []
    for endpoint_id, observations in endpoint_versions.items():
        first_version, first_endpoint = observations[0]
        last_version, last_endpoint = observations[-1]
        current_present = endpoint_id in latest_endpoint_ids
        route = routes.get(endpoint_id) if current_present else None
        if current_present and route is None:
            raise ValueError(f"Current protobuf endpoint has no reader route: {endpoint_id}")

        changes = tuple(
            ChangeDetail(
                version=version,
                summary=_change_summary(change_types),
                evidence=(
                    Evidence(
                        kind=EvidenceKind.SNAPSHOT_DIFF,
                        source=_source(current, report=report, version=version),
                        observed_in_version=version,
                        location=_location(current),
                    ),
                ),
            )
            for version, change_types, current in modified_by_id.get(endpoint_id, [])
        )

        observed_removal = None
        removal_evidence = None
        if not current_present:
            last_index = comparison_versions.index(last_version)
            observed_removal = comparison_versions[last_index + 1]
            removal_evidence = Evidence(
                kind=EvidenceKind.SNAPSHOT_DIFF,
                source=_source(last_endpoint, report=report, version=observed_removal),
                observed_in_version=observed_removal,
                location=_location(last_endpoint),
                detail="The endpoint is absent from this descriptor snapshot.",
            )

        items.append(
            HistoryItem(
                id=endpoint_id,
                kind="grpc_endpoint" if format == ReferenceFormat.GRPC else "protobuf_endpoint",
                route=route,
                location=_location(last_endpoint),
                first_seen=first_version,
                last_seen=last_version,
                current_present=current_present,
                introduction_evidence=Evidence(
                    kind=EvidenceKind.SNAPSHOT,
                    source=_source(first_endpoint, report=report, version=first_version),
                    observed_in_version=first_version,
                    location=_location(first_endpoint),
                ),
                observed_removal=observed_removal,
                removal_evidence=removal_evidence,
                last_changed=changes[-1].version if changes else None,
                changes=changes,
            )
        )

    repo = report.get("repo") or {}
    repo_web_url = str(repo.get("webUrl") or repo.get("remote") or report["sourceName"])
    return SurfaceHistoryReport(
        surface_id=surface_id,
        title=title,
        format=format,
        configured_scope=configured_scope,
        history_mode=HistoryMode.SNAPSHOTS,
        publish_version=publish_version,
        comparison_versions=comparison_versions,
        source_artifacts=tuple(
            SourceArtifact(
                version=str(release["version"]),
                source=f"{repo_web_url}/tree/{release['tag']}",
                revision=str(release["tag"]),
            )
            for release in releases
        ),
        version_policy=VersionSelectionPolicy.LATEST_SELECTED_RELEASE,
        items=tuple(sorted(items, key=lambda item: item.id)),
        limitations=(
            "Descriptor snapshots establish endpoint additions, updates, and removals; authored deprecation and scheduled-removal metadata is not present in this source.",
        ),
    )


def _source(endpoint: dict[str, Any], *, report: dict[str, Any], version: str) -> str:
    source_url = endpoint.get("sourceUrl")
    if source_url:
        return str(source_url)
    repo = report.get("repo") or {}
    return str(repo.get("webUrl") or repo.get("remote") or f"protobuf snapshot {version}")


def _location(endpoint: dict[str, Any]) -> str:
    return f"/{endpoint['serviceFullName']}/{endpoint['name']}"


def _change_summary(change_types: list[str]) -> str:
    labels = {
        "request": "request type updated",
        "response": "response type updated",
        "streaming": "streaming contract updated",
        "description": "description updated",
        "endpoint": "endpoint contract updated",
    }
    details = [labels.get(change_type, f"{change_type.replace('_', ' ')} updated") for change_type in change_types]
    return "; ".join(details) or "Endpoint contract updated."
