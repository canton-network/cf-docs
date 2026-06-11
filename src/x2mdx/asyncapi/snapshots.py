"""Load supplied AsyncAPI snapshots from local manifests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from x2mdx.asyncapi.lifecycle import parse_asyncapi, version_key
from x2mdx.asyncapi.models import AsyncApiSourceSnapshot
from x2mdx.types import JsonValue, require_json_object, require_json_value


def _load_data(path: Path) -> JsonValue:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return require_json_value(json.loads(raw), path=str(path))
    return require_json_value(yaml.safe_load(raw), path=str(path))


def load_snapshot_manifest(path: Path) -> dict[str, JsonValue]:
    data = require_json_object(_load_data(path), path=str(path))
    versions = data.get("versions")
    if not isinstance(versions, list):
        raise ValueError("Snapshot manifest must include a `versions` list")
    return data


def load_asyncapi_source_snapshots(
    manifest_path: Path,
    *,
    fixture_root: Path | None = None,
    include_versions: set[str] | None = None,
) -> list[AsyncApiSourceSnapshot]:
    manifest = load_snapshot_manifest(manifest_path)
    root = fixture_root or manifest_path.parent
    versions = manifest.get("versions")
    if not isinstance(versions, list):
        raise ValueError("Snapshot manifest must include a `versions` list")

    snapshots: list[AsyncApiSourceSnapshot] = []
    for entry in versions:
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        fixture_path = entry.get("fixture_path")
        if not isinstance(version, str) or not version:
            continue
        if include_versions is not None and version not in include_versions:
            continue
        if not isinstance(fixture_path, str) or not fixture_path:
            continue

        source_path = entry.get("source_path")
        if not isinstance(source_path, str) or not source_path:
            source_path = fixture_path

        document_path = root / fixture_path
        document = parse_asyncapi(document_path.read_text(encoding="utf-8"))
        snapshots.append(
            AsyncApiSourceSnapshot(
                version=version,
                source_path=source_path,
                document=document,
            )
        )

    snapshots.sort(key=lambda snapshot: version_key(snapshot.version))
    return snapshots
