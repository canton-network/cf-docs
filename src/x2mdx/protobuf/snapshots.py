"""Load protobuf descriptor-image snapshots from a manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import yaml

from x2mdx.protobuf.models import ProtobufSourceSnapshot, ProtobufSources
from x2mdx.types import JsonObject

DEFAULT_METADATA_SHAPE = {
    "schemaVersion": 1,
    "files": {},
    "services": {},
    "endpoints": {},
    "messages": {},
    "fields": {},
    "enums": {},
    "enumValues": {},
}


def _load_manifest(path: Path) -> JsonObject:
    if path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object at manifest root: {path}")
    return cast(JsonObject, payload)


def _load_metadata_overlay(path: Path | None) -> JsonObject:
    data = cast(JsonObject, json.loads(json.dumps(DEFAULT_METADATA_SHAPE)))
    if path is None or not path.exists():
        return data
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in data:
        if key == "schemaVersion":
            data[key] = raw.get(key, data[key])
            continue
        value = raw.get(key, {})
        if isinstance(value, dict):
            data[key] = value
    return data


def load_protobuf_sources(
    manifest_path: Path,
    *,
    fixture_root: Path | None = None,
    include_versions: set[str] | None = None,
) -> ProtobufSources:
    manifest = _load_manifest(manifest_path)
    manifest_root = fixture_root or manifest_path.parent
    versions = manifest.get("versions")
    if not isinstance(versions, list):
        raise ValueError("Manifest must contain a `versions` list")

    snapshots: list[ProtobufSourceSnapshot] = []
    for entry in versions:
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        tag = entry.get("tag")
        raw_image_path = entry.get("descriptor_image_path")
        import_to_repo_path = entry.get("import_to_repo_path")
        if not isinstance(version, str) or not version:
            continue
        if include_versions is not None and version not in include_versions:
            continue
        if not isinstance(tag, str) or not tag:
            continue
        if not isinstance(raw_image_path, str) or not raw_image_path:
            continue
        if not isinstance(import_to_repo_path, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in import_to_repo_path.items()
        ):
            raise ValueError(f"Manifest entry for protobuf version {version} must define string import_to_repo_path")

        image_path = Path(raw_image_path)
        if not image_path.is_absolute():
            image_path = manifest_root / image_path
        snapshots.append(
            ProtobufSourceSnapshot(
                version=version,
                tag=tag,
                date=entry.get("date") if isinstance(entry.get("date"), str) else None,
                descriptor_image_path=str(image_path.resolve()),
                import_to_repo_path=dict(import_to_repo_path),
            )
        )

    if not snapshots:
        raise ValueError("No protobuf snapshots selected from manifest")

    metadata_path = manifest.get("metadata_path")
    resolved_metadata_path: Path | None = None
    if isinstance(metadata_path, str) and metadata_path:
        resolved_metadata_path = Path(metadata_path)
        if not resolved_metadata_path.is_absolute():
            resolved_metadata_path = manifest_root / resolved_metadata_path

    raw_repo = manifest.get("repo")
    repo: JsonObject = raw_repo if isinstance(raw_repo, dict) else {}
    return ProtobufSources(
        snapshots=snapshots,
        source=manifest.get("source") if isinstance(manifest.get("source"), str) else None,
        repo_remote=repo.get("remote") if isinstance(repo.get("remote"), str) else None,
        repo_web_url=repo.get("web_url") if isinstance(repo.get("web_url"), str) else None,
        metadata_overlay=_load_metadata_overlay(resolved_metadata_path),
    )
