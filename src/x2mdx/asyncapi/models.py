"""Format-specific input-side models for AsyncAPI processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AsyncApiSourceSnapshot:
    version: str
    source_path: str
    document: dict[str, Any]


@dataclass(frozen=True)
class AsyncApiChannelLifecycle:
    channel: str
    anchor: str
    introduced_version: str
    changed_in_versions: list[str]
    change_details: list[dict[str, Any]]
    removed_version: str | None
    last_seen_in: str
    status: str
    lifecycle_state: str | None
    replaces: str | None
    latest: dict[str, Any]


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
