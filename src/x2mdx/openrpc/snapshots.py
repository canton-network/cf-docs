"""Load supplied OpenRPC snapshots from local manifests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from x2mdx.openrpc.lifecycle import parse_openrpc, version_key
from x2mdx.openrpc.models import OpenRpcSourceSnapshot
from x2mdx.types import JsonValue, require_json_object, require_json_value


def _load_data(path: Path) -> JsonValue:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return require_json_value(json.loads(raw), path=str(path))
    return require_json_value(yaml.safe_load(raw), path=str(path))


def load_snapshot_manifest(path: Path) -> dict[str, JsonValue]:
    data = require_json_object(_load_data(path), path=str(path))
    specs = data.get("specs")
    if not isinstance(specs, list):
        raise ValueError("Snapshot manifest must include a `specs` list")
    return data


def load_openrpc_source_snapshots(
    manifest_path: Path,
    *,
    fixture_root: Path | None = None,
    include_versions: set[str] | None = None,
) -> list[OpenRpcSourceSnapshot]:
    manifest = load_snapshot_manifest(manifest_path)
    root = fixture_root or manifest_path.parent
    specs = manifest.get("specs")
    if not isinstance(specs, list):
        raise ValueError("Snapshot manifest must include a `specs` list")

    snapshots: list[OpenRpcSourceSnapshot] = []
    for spec_entry in specs:
        if not isinstance(spec_entry, dict):
            continue
        spec_id = spec_entry.get("spec_id")
        versions = spec_entry.get("versions")
        if not isinstance(spec_id, str) or not spec_id:
            continue
        if not isinstance(versions, list):
            continue
        display_name = spec_entry.get("display_name")
        if not isinstance(display_name, str) or not display_name:
            display_name = spec_id

        default_source_path = spec_entry.get("source_path")
        for version_entry in versions:
            if not isinstance(version_entry, dict):
                continue
            version = version_entry.get("version")
            fixture_path = version_entry.get("fixture_path")
            if not isinstance(version, str) or not version:
                continue
            if include_versions is not None and version not in include_versions:
                continue
            if not isinstance(fixture_path, str) or not fixture_path:
                continue

            source_path = version_entry.get("source_path")
            if not isinstance(source_path, str) or not source_path:
                source_path = default_source_path if isinstance(default_source_path, str) and default_source_path else fixture_path

            document_path = root / fixture_path
            document = parse_openrpc(document_path.read_text(encoding="utf-8"))
            snapshots.append(
                OpenRpcSourceSnapshot(
                    version=version,
                    spec_id=spec_id,
                    display_name=display_name,
                    source_path=source_path,
                    document=document,
                )
            )

    snapshots.sort(key=lambda snapshot: (version_key(snapshot.version), snapshot.spec_id))
    return snapshots
