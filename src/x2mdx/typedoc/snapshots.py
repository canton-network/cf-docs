"""Load versioned TypeDoc JSON snapshots from a manifest."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from x2mdx.typedoc.models import TypeDocDocument, TypeDocSnapshot, TypeDocSources
from x2mdx.types import JsonValue, require_json_object


def _load_manifest(path: Path) -> dict[str, JsonValue]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    return require_json_object(payload, path=str(path))


def _optional_string(payload: dict[str, JsonValue], key: str, path: Path) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Expected string `{key}` in {path}")
    return value


def _optional_json_list(payload: dict[str, JsonValue], key: str, path: Path) -> list[JsonValue] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"Expected list `{key}` in {path}")
    return value


def _load_document(path: Path) -> TypeDocDocument:
    payload = require_json_object(json.loads(path.read_text(encoding="utf-8")), path=str(path))
    document: TypeDocDocument = {}
    package_name = _optional_string(payload, "packageName", path)
    if package_name is not None:
        document["packageName"] = package_name
    name = _optional_string(payload, "name", path)
    if name is not None:
        document["name"] = name
    groups = _optional_json_list(payload, "groups", path)
    if groups is not None:
        document["groups"] = groups
    children = _optional_json_list(payload, "children", path)
    if children is not None:
        document["children"] = children
    return document


def load_typedoc_sources(
    manifest_path: Path,
    *,
    fixture_root: Path | None = None,
    include_versions: set[str] | None = None,
) -> TypeDocSources:
    manifest = _load_manifest(manifest_path)
    manifest_root = fixture_root or manifest_path.parent
    versions = manifest.get("versions")
    if not isinstance(versions, list):
        raise ValueError("Manifest must contain a `versions` list")

    snapshots: list[TypeDocSnapshot] = []
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
        resolved = json_path.resolve()
        snapshots.append(
            TypeDocSnapshot(
                version=version,
                json_path=str(resolved),
                document=_load_document(resolved),
            )
        )

    if not snapshots:
        raise ValueError("No TypeDoc snapshots selected from manifest")

    publish_version = manifest.get("publish_version")
    if publish_version is not None and not isinstance(publish_version, str):
        raise ValueError("Manifest `publish_version` must be a string when present")

    package_name = manifest.get("package_name")
    if package_name is not None and not isinstance(package_name, str):
        raise ValueError("Manifest `package_name` must be a string when present")

    source = manifest.get("source")
    if source is not None and not isinstance(source, str):
        raise ValueError("Manifest `source` must be a string when present")

    return TypeDocSources(
        snapshots=snapshots,
        publish_version=publish_version,
        source=source,
        package_name=package_name,
    )
