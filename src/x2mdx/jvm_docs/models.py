"""Format-specific input and report models for JVM API docs."""

from __future__ import annotations

from dataclasses import dataclass, field

JVM_DOC_OBJECT_STATUSES = frozenset({"alpha", "beta", "stable", "deprecated"})


@dataclass(frozen=True)
class JvmDocVersionSource:
    version: str
    jar_path: str


@dataclass(frozen=True)
class JvmDocArtifactSource:
    group: str
    artifact: str
    language: str
    include_prefixes: list[str] = field(default_factory=list)
    versions: list[JvmDocVersionSource] = field(default_factory=list)
    type_statuses: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class JvmDocSymbolLifecycle:
    symbol_key: str
    language: str
    kind: str
    symbol: str
    introduced_version: str
    deprecated_version: str | None
    removed_version: str | None
    versions_present: list[str]
    doc_links: dict[str, str]
    latest_doc_path: str
    status: str | None = None
    deprecation_note: str | None = None
    latest_signature: str | None = None
    latest_summary: str | None = None


@dataclass(frozen=True)
class JvmDocArtifactLifecycle:
    group: str
    artifact: str
    language: str
    versions: list[str]
    symbol_count: int
    type_count: int
    member_count: int
    failures: list[dict[str, str]]
    symbols: list[JvmDocSymbolLifecycle]


@dataclass(frozen=True)
class JvmDocLifecycleReport:
    source_name: str
    version_filter: str
    summary: dict[str, int]
    notes: list[str]
    artifacts: list[JvmDocArtifactLifecycle]
