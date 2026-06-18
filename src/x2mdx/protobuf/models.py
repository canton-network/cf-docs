"""Models for descriptor-backed protobuf source snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from x2mdx.types import JsonValue


class ProtobufMetadataOverlay(TypedDict, total=False):
    schemaVersion: int
    files: dict[str, JsonValue]
    services: dict[str, JsonValue]
    endpoints: dict[str, JsonValue]
    messages: dict[str, JsonValue]
    fields: dict[str, JsonValue]
    enums: dict[str, JsonValue]
    enumValues: dict[str, JsonValue]


@dataclass(frozen=True)
class ProtobufSourceSnapshot:
    version: str
    tag: str
    date: str | None
    descriptor_image_path: str
    import_to_repo_path: dict[str, str]


@dataclass(frozen=True)
class ProtobufSources:
    snapshots: list[ProtobufSourceSnapshot]
    source: str | None = None
    repo_remote: str | None = None
    repo_web_url: str | None = None
    metadata_overlay: ProtobufMetadataOverlay | None = None
