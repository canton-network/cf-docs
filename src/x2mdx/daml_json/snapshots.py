"""Load versioned Daml docs JSON snapshots from a manifest."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from x2mdx.daml_json.models import DamlDocsSnapshot, DamlDocsSources, DamlJsonModule
from x2mdx.types import JsonValue, require_json_object, require_json_value


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


def _load_module_payload(payload: dict[str, JsonValue], path: Path) -> DamlJsonModule:
    name = _optional_string(payload, "md_name", path)
    if not name:
        raise ValueError(f"Expected non-empty string `md_name` in {path}")

    module: DamlJsonModule = {"md_name": name}
    anchor = _optional_string(payload, "md_anchor", path)
    if anchor is not None:
        module["md_anchor"] = anchor
    if "md_descr" in payload:
        module["md_descr"] = payload["md_descr"]
    if "md_warn" in payload:
        module["md_warn"] = payload["md_warn"]

    md_adts = _optional_json_list(payload, "md_adts", path)
    if md_adts is not None:
        module["md_adts"] = md_adts
    md_classes = _optional_json_list(payload, "md_classes", path)
    if md_classes is not None:
        module["md_classes"] = md_classes
    md_functions = _optional_json_list(payload, "md_functions", path)
    if md_functions is not None:
        module["md_functions"] = md_functions
    md_interfaces = _optional_json_list(payload, "md_interfaces", path)
    if md_interfaces is not None:
        module["md_interfaces"] = md_interfaces
    md_templates = _optional_json_list(payload, "md_templates", path)
    if md_templates is not None:
        module["md_templates"] = md_templates
    md_instances = _optional_json_list(payload, "md_instances", path)
    if md_instances is not None:
        module["md_instances"] = md_instances
    return module


def _load_modules(path: Path) -> list[DamlJsonModule]:
    payload = require_json_value(json.loads(path.read_text(encoding="utf-8")), path=str(path))
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError(f"Expected top-level JSON list or object in {path}")
    modules: list[DamlJsonModule] = []
    for index, item in enumerate(payload):
        if isinstance(item, dict):
            modules.append(_load_module_payload(item, path))
        else:
            raise ValueError(f"Expected module object at {path}[{index}]")
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
        source=source if isinstance((source := manifest.get("source")), str) else None,
    )
