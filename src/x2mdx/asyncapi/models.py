"""Format-specific input-side models for AsyncAPI processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from x2mdx.types import JsonObject, JsonValue


class AsyncApiDocument(TypedDict, total=False):
    asyncapi: str
    info: JsonObject
    channels: dict[str, JsonValue]
    components: JsonObject


class AsyncApiMessageDetail(TypedDict):
    name: str
    content_type: str
    payload_schema: str
    required_fields: list[str]
    sample: JsonValue | None


class AsyncApiActionDetail(TypedDict):
    action: str
    operation_id: str
    description: str
    ws_method: str
    message: AsyncApiMessageDetail


class AsyncApiChannelDetail(TypedDict):
    channel: str
    anchor: str
    description: str
    lifecycle_state: str | None
    replaces: str | None
    actions: list[AsyncApiActionDetail]
    action_names: list[str]


class AsyncApiChangeDetail(TypedDict):
    version: str
    changes: list[str]


class AsyncApiChannelHistory(TypedDict):
    versions: list[str]
    details: dict[str, AsyncApiChannelDetail]
    fingerprints: dict[str, str]
    changed_in: list[str]
    change_details: list[AsyncApiChangeDetail]


@dataclass(frozen=True)
class AsyncApiSourceSnapshot:
    version: str
    source_path: str
    document: AsyncApiDocument


@dataclass(frozen=True)
class AsyncApiChannelLifecycle:
    channel: str
    anchor: str
    introduced_version: str
    changed_in_versions: list[str]
    change_details: list[AsyncApiChangeDetail]
    removed_version: str | None
    last_seen_in: str
    status: str
    lifecycle_state: str | None
    replaces: str | None
    latest: AsyncApiChannelDetail


@dataclass(frozen=True)
class AsyncApiReport:
    source_name: str
    version_filter: str
    versions: list[str]
    publish_version: str
    asyncapi_version: str | None
    info_title: str | None
    info_description: str | None
    latest_source_path: str
    per_version_deltas: dict[str, dict[str, int]]
    channels: list[AsyncApiChannelLifecycle]
