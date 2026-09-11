from __future__ import annotations

from collections.abc import Mapping

from x2mdx.history.models import (
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
from x2mdx.jvm_docs.models import JvmDocLifecycleReport


def build_jvm_surface_history_report(
    report: JvmDocLifecycleReport,
    *,
    routes: Mapping[str, str],
    surface_id: str,
    title: str,
    configured_scope: str,
) -> SurfaceHistoryReport:
    """Normalize Java type lifecycles into the shared history contract."""
    if not report.artifacts:
        raise ValueError("JVM history requires at least one artifact")

    version_sets = {tuple(artifact.versions) for artifact in report.artifacts}
    if len(version_sets) != 1:
        raise ValueError("A JVM history surface requires one shared ordered version window")
    comparison_versions = next(iter(version_sets))
    if not comparison_versions:
        raise ValueError("JVM history requires at least one comparison version")
    publish_version = comparison_versions[-1]

    items: list[HistoryItem] = []
    source_artifacts: list[SourceArtifact] = []
    for artifact in report.artifacts:
        for version in artifact.versions:
            source_artifacts.append(
                SourceArtifact(
                    version=version,
                    source=(
                        "https://javadoc.io/doc/"
                        f"{artifact.group}/{artifact.artifact}/{version}/"
                    ),
                    revision=version,
                )
            )

        for symbol in artifact.symbols:
            if symbol.kind != "type":
                continue
            current_present = (
                symbol.removed_version is None
                and publish_version in symbol.versions_present
            )
            route = routes.get(symbol.symbol_key) if current_present else None
            if current_present and route is None:
                raise ValueError(
                    f"Current Java type has no reader route: {symbol.symbol_key}"
                )

            introduction_source = symbol.doc_links[symbol.introduced_version]
            removal_evidence = None
            if symbol.removed_version is not None:
                removal_evidence = Evidence(
                    kind=EvidenceKind.SNAPSHOT_DIFF,
                    source=symbol.doc_links[symbol.versions_present[-1]],
                    observed_in_version=symbol.removed_version,
                    location=symbol.symbol,
                    detail="The type is absent from this Javadoc snapshot.",
                )

            transitions: tuple[LifecycleTransition, ...] = ()
            lifecycle_state = None
            if symbol.deprecated_version is not None:
                deprecation_source = symbol.doc_links.get(
                    symbol.deprecated_version,
                    symbol.doc_links[symbol.versions_present[-1]],
                )
                transitions = (
                    LifecycleTransition(
                        state=LifecycleState.DEPRECATED,
                        version=symbol.deprecated_version,
                        evidence=Evidence(
                            kind=EvidenceKind.SOURCE_METADATA,
                            source=deprecation_source,
                            observed_in_version=symbol.deprecated_version,
                            location=symbol.symbol,
                            detail=symbol.deprecation_note,
                        ),
                    ),
                )
                lifecycle_state = LifecycleState.DEPRECATED

            items.append(
                HistoryItem(
                    id=symbol.symbol_key,
                    kind="java_type",
                    route=route,
                    location=symbol.symbol,
                    first_seen=symbol.introduced_version,
                    last_seen=symbol.versions_present[-1],
                    current_present=current_present,
                    introduction_evidence=Evidence(
                        kind=EvidenceKind.SNAPSHOT,
                        source=introduction_source,
                        observed_in_version=symbol.introduced_version,
                        location=symbol.symbol,
                    ),
                    observed_removal=symbol.removed_version,
                    removal_evidence=removal_evidence,
                    lifecycle_state=lifecycle_state,
                    lifecycle_transitions=transitions,
                )
            )

    return SurfaceHistoryReport(
        surface_id=surface_id,
        title=title,
        format=ReferenceFormat.JVM_DOCS,
        configured_scope=configured_scope,
        history_mode=HistoryMode.SNAPSHOTS,
        publish_version=publish_version,
        comparison_versions=comparison_versions,
        source_artifacts=tuple(source_artifacts),
        version_policy=VersionSelectionPolicy.LATEST_SELECTED_RELEASE,
        items=tuple(sorted(items, key=lambda item: item.id)),
        limitations=(
            "Javadoc snapshots establish type additions, authored deprecations, and removals; signature and prose-only updates are not yet classified as Updated events.",
            "Scheduled-removal metadata is not present in the selected Javadoc source.",
        ),
    )
