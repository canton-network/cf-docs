"""Load versioned Daml docs JSON snapshots from a manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import yaml

from x2mdx.daml_json.models import DamlDocsSnapshot, DamlDocsSources, DamlJsonModule
from x2mdx.types import JsonObject


def _load_manifest(path: Path) -> JsonObject:
    if path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object at manifest root: {path}")
    return cast(JsonObject, payload)


def _load_modules(path: Path) -> list[DamlJsonModule]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError(f"Expected top-level JSON list or object in {path}")
    modules: list[DamlJsonModule] = []
    for item in payload:
        if isinstance(item, dict):
            modules.append(cast(DamlJsonModule, item))
    return modules


def load_daml_doc_sources(
    manifest_path: Path,
    *,
    fixture_root: Path | None = None,
    include_versions: set[str] | None = None,
) -> DamlDocsSources:
    manifest = _load_manifest(manifest_path)
    manifest_root = fixture_root or manifest_path.parent
    versions = manifest.get("versions")
    if not isinstance(versions, list):
        raise ValueError("Manifest must contain a `versions` list")

    snapshots: list[DamlDocsSnapshot] = []
    for entry in versions:
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        raw_json_path = entry.get("json_path")
        if not isinstance(version, str) or not version:
            continue
        if include_versions is not None and version not in include_versions:
            continue
        if not isinstance(raw_json_path, str) or not raw_json_path:
            continue
        json_path = Path(raw_json_path)
        if not json_path.is_absolute():
            json_path = manifest_root / json_path
        snapshots.append(
            DamlDocsSnapshot(
                version=version,
                json_path=str(json_path.resolve()),
                modules=_load_modules(json_path.resolve()),
            )
        )

    if not snapshots:
        raise ValueError("No Daml docs snapshots selected from manifest")

    publish_version = manifest.get("publish_version")
    if publish_version is not None and not isinstance(publish_version, str):
        raise ValueError("Manifest `publish_version` must be a string when present")

    return DamlDocsSources(
        snapshots=snapshots,
        publish_version=publish_version,
        source=manifest.get("source") if isinstance(manifest.get("source"), str) else None,
    )
