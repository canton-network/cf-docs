"""Models for descriptor-backed protobuf source snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from x2mdx.types import JsonObject


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
    metadata_overlay: JsonObject | None = None
