"""Load protobuf descriptor-image snapshots from a manifest."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from x2mdx.protobuf.models import ProtobufMetadataOverlay, ProtobufSourceSnapshot, ProtobufSources
from x2mdx.types import JsonValue, require_json_object

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


def _load_manifest(path: Path) -> dict[str, JsonValue]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    return require_json_object(payload, path=str(path))


def _load_metadata_overlay(path: Path | None) -> ProtobufMetadataOverlay:
    data: ProtobufMetadataOverlay = {
        "schemaVersion": 1,
        "files": {},
        "services": {},
        "endpoints": {},
        "messages": {},
        "fields": {},
        "enums": {},
        "enumValues": {},
    }
    if path is None or not path.exists():
        return data

    raw = require_json_object(json.loads(path.read_text(encoding="utf-8")), path=str(path))
    schema_version = raw.get("schemaVersion")
    if schema_version is not None:
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise ValueError(f"Expected integer `schemaVersion` in {path}")
        data["schemaVersion"] = schema_version

    files = raw.get("files")
    if files is not None:
        if not isinstance(files, dict):
            raise ValueError(f"Expected object `files` in {path}")
        data["files"] = files
    services = raw.get("services")
    if services is not None:
        if not isinstance(services, dict):
            raise ValueError(f"Expected object `services` in {path}")
        data["services"] = services
    endpoints = raw.get("endpoints")
    if endpoints is not None:
        if not isinstance(endpoints, dict):
            raise ValueError(f"Expected object `endpoints` in {path}")
        data["endpoints"] = endpoints
    messages = raw.get("messages")
    if messages is not None:
        if not isinstance(messages, dict):
            raise ValueError(f"Expected object `messages` in {path}")
        data["messages"] = messages
    fields = raw.get("fields")
    if fields is not None:
        if not isinstance(fields, dict):
            raise ValueError(f"Expected object `fields` in {path}")
        data["fields"] = fields
    enums = raw.get("enums")
    if enums is not None:
        if not isinstance(enums, dict):
            raise ValueError(f"Expected object `enums` in {path}")
        data["enums"] = enums
    enum_values = raw.get("enumValues")
    if enum_values is not None:
        if not isinstance(enum_values, dict):
            raise ValueError(f"Expected object `enumValues` in {path}")
        data["enumValues"] = enum_values
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
        raw_import_to_repo_path = entry.get("import_to_repo_path")
        if not isinstance(version, str) or not version:
            continue
        if include_versions is not None and version not in include_versions:
            continue
        if not isinstance(tag, str) or not tag:
            continue
        if not isinstance(raw_image_path, str) or not raw_image_path:
            continue
        if not isinstance(raw_import_to_repo_path, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw_import_to_repo_path.items()
        ):
            raise ValueError(f"Manifest entry for protobuf version {version} must define string import_to_repo_path")
        import_to_repo_path = {str(key): str(value) for key, value in raw_import_to_repo_path.items()}
        date = entry.get("date")

        image_path = Path(raw_image_path)
        if not image_path.is_absolute():
            image_path = manifest_root / image_path
        snapshots.append(
            ProtobufSourceSnapshot(
                version=version,
                tag=tag,
                date=date if isinstance(date, str) else None,
                descriptor_image_path=str(image_path.resolve()),
                import_to_repo_path=import_to_repo_path,
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
    repo = raw_repo if isinstance(raw_repo, dict) else {}
    source = manifest.get("source")
    repo_remote = repo.get("remote")
    repo_web_url = repo.get("web_url")
    return ProtobufSources(
        snapshots=snapshots,
        source=source if isinstance(source, str) else None,
        repo_remote=repo_remote if isinstance(repo_remote, str) else None,
        repo_web_url=repo_web_url if isinstance(repo_web_url, str) else None,
        metadata_overlay=_load_metadata_overlay(resolved_metadata_path),
    )
