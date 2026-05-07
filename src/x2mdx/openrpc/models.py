"""Format-specific input-side models for OpenRPC processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OpenRpcSourceSnapshot:
    version: str
    spec_id: str
    display_name: str
    source_path: str
    document: dict[str, Any]


@dataclass(frozen=True)
class OpenRpcMethodLifecycle:
    method: str
    anchor: str
    introduced_version: str
    changed_in_versions: list[str]
    change_details: list[dict[str, Any]]
    removed_version: str | None
    last_seen_in: str
    status: str
    latest: dict[str, Any]


@dataclass(frozen=True)
class OpenRpcSpecLifecycle:
    spec_id: str
    display_name: str
    latest_source_path: str
    introduced_version: str
    changed_in_versions: list[str]
    removed_version: str | None
    versions_present: list[str]
    latest_version: str
    openrpc_version: str | None
    info_title: str | None
    info_version: str | None
    info_description: str | None
    per_version_method_deltas: dict[str, dict[str, int]]
    methods: list[OpenRpcMethodLifecycle]


@dataclass(frozen=True)
class OpenRpcReport:
    source_name: str
    version_filter: str
    versions: list[str]
    publish_version: str
    specs: list[OpenRpcSpecLifecycle]
