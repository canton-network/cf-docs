from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HistoryMode(StrEnum):
    SNAPSHOTS = "snapshots"
    AUTHORED = "authored"
    UNAVAILABLE = "unavailable"


class ReferenceFormat(StrEnum):
    OPENAPI = "openapi"
    ASYNCAPI = "asyncapi"
    GRPC = "grpc"
    PROTOBUF = "protobuf"
    JVM_DOCS = "jvm_docs"
    DAML_JSON = "daml_json"
    OPENRPC = "openrpc"
    TYPEDOC = "typedoc"


class VersionSelectionPolicy(StrEnum):
    CONFIGURED_PUBLISH_VERSION = "configured_publish_version"
    CONFIGURED_PUBLISH_VERSION_PER_PACKAGE = "configured_publish_version_per_package"
    LATEST_CONFIGURED_VERSION_PER_ARTIFACT = "latest_configured_version_per_artifact"
    LATEST_SELECTED_RELEASE = "latest_selected_release"


class EvidenceKind(StrEnum):
    SNAPSHOT = "snapshot"
    SNAPSHOT_DIFF = "snapshot_diff"
    SOURCE_METADATA = "source_metadata"
    SIDECAR = "sidecar"


class IdentityConfidence(StrEnum):
    EXACT = "exact"
    FALLBACK = "fallback"


class LifecycleState(StrEnum):
    ALPHA = "alpha"
    BETA = "beta"
    STABLE = "stable"
    DEPRECATED = "deprecated"


class HistoryEventKind(StrEnum):
    REMOVE_AS_OF = "remove_as_of"
    DEPRECATED = "deprecated"
    CHANGED = "changed"
    INTRODUCED = "introduced"
    REPLACEMENT = "replacement"


@dataclass(frozen=True)
class Evidence:
    kind: EvidenceKind
    source: str
    observed_in_version: str
    location: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class SourceArtifact:
    version: str
    source: str
    revision: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class ChangeDetail:
    version: str
    summary: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class LifecycleTransition:
    state: LifecycleState
    version: str
    evidence: Evidence


@dataclass(frozen=True)
class ReplacementEdge:
    from_item_id: str
    to_item_id: str
    version: str
    evidence: Evidence


@dataclass(frozen=True)
class HistoryItem:
    id: str
    kind: str
    route: str | None
    location: str | None
    first_seen: str
    last_seen: str
    current_present: bool
    introduction_evidence: Evidence
    observed_removal: str | None = None
    removal_evidence: Evidence | None = None
    last_changed: str | None = None
    changes: tuple[ChangeDetail, ...] = ()
    lifecycle_state: LifecycleState | None = None
    lifecycle_transitions: tuple[LifecycleTransition, ...] = ()
    remove_as_of: str | None = None
    remove_as_of_evidence: Evidence | None = None
    replacement_edges: tuple[ReplacementEdge, ...] = ()
    identity_confidence: IdentityConfidence = IdentityConfidence.EXACT
    identity_evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class SurfaceHistoryReport:
    surface_id: str
    title: str
    format: ReferenceFormat
    configured_scope: str
    history_mode: HistoryMode
    publish_version: str
    comparison_versions: tuple[str, ...]
    source_artifacts: tuple[SourceArtifact, ...]
    version_policy: VersionSelectionPolicy
    items: tuple[HistoryItem, ...]
    limitations: tuple[str, ...] = ()

    def items_by_id(self) -> dict[str, HistoryItem]:
        return {item.id: item for item in self.items}

    def current_items(self) -> tuple[HistoryItem, ...]:
        return tuple(item for item in self.items if item.current_present)


@dataclass(frozen=True)
class HistoryEvent:
    kind: HistoryEventKind
    version: str
    label: str
    details: tuple[str, ...]
    evidence: tuple[Evidence, ...]
