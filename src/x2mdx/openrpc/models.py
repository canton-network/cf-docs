"""Format-specific input-side models for OpenRPC processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from x2mdx.types import JsonValue


class OpenRpcDocument(TypedDict, total=False):
    openrpc: str
    info: dict[str, JsonValue]
    methods: list[dict[str, JsonValue]]
    components: dict[str, JsonValue]


class OpenRpcParamDetail(TypedDict):
    name: str
    description: str
    schema_name: str | None
    schema: str
    required_fields: list[str]
    sample: JsonValue | None


class OpenRpcResultDetail(TypedDict):
    name: str
    description: str
    schema_name: str | None
    schema: str
    required_fields: list[str]
    sample: JsonValue | None


class OpenRpcMethodDetail(TypedDict):
    name: str
    anchor: str
    summary: str
    description: str
    lifecycle_state: str | None
    replaces: str | None
    params: list[OpenRpcParamDetail]
    result: OpenRpcResultDetail
    fingerprint: str


class OpenRpcChangeDetail(TypedDict):
    version: str
    changes: list[str]


class OpenRpcMethodHistory(TypedDict):
    versions: list[str]
    details: dict[str, OpenRpcMethodDetail]
    fingerprints: dict[str, str]
    changed_in: list[str]
    change_details: list[OpenRpcChangeDetail]


@dataclass(frozen=True)
class OpenRpcSourceSnapshot:
    version: str
    spec_id: str
    display_name: str
    source_path: str
    document: OpenRpcDocument


@dataclass(frozen=True)
class OpenRpcMethodLifecycle:
    method: str
    anchor: str
    introduced_version: str
    changed_in_versions: list[str]
    change_details: list[OpenRpcChangeDetail]
    removed_version: str | None
    last_seen_in: str
    status: str
    lifecycle_state: str | None
    replaces: str | None
    latest: OpenRpcMethodDetail


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
