"""Models for descriptor-backed protobuf source snapshots."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProtobufSourceSnapshot:
    version: str
    tag: str
    date: str | None
    descriptor_image_path: str
    import_to_repo_path: dict[str, str]
    # Paths that exist at `tag`, for source links. `import_to_repo_path` stays the
    # cross-release identity. When set, files missing from it get no source link.
    import_to_source_path: dict[str, str] | None = None


@dataclass(frozen=True)
class ProtobufSources:
    snapshots: list[ProtobufSourceSnapshot]
    source: str | None = None
    repo_remote: str | None = None
    repo_web_url: str | None = None
