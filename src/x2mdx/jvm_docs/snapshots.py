"""Load supplied JVM doc snapshots from local manifests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from x2mdx.jvm_docs.lifecycle import version_key
from x2mdx.jvm_docs.models import JvmDocArtifactSource, JvmDocVersionSource, JVM_DOC_OBJECT_STATUSES
from x2mdx.types import JsonValue, require_json_object, require_json_value


def _load_data(path: Path) -> JsonValue:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return require_json_value(json.loads(raw), path=str(path))
    return require_json_value(yaml.safe_load(raw), path=str(path))


def load_jvm_doc_manifest(path: Path) -> dict[str, JsonValue]:
    data = require_json_object(_load_data(path), path=str(path))
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("JVM doc manifest must include an `artifacts` list")
    return data


def load_jvm_doc_status_manifest(path: Path) -> dict[str, str]:
    data = _load_data(path)
    if not isinstance(data, dict):
        raise ValueError("JVM doc status manifest must be a JSON/YAML object")

    raw_types = data.get("types")
    if not isinstance(raw_types, dict):
        raise ValueError("JVM doc status manifest must include a `types` mapping")

    statuses: dict[str, str] = {}
    for symbol, payload in raw_types.items():
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(f"JVM doc status manifest contains a non-string type key: {path}")
        if not isinstance(payload, dict):
            raise ValueError(f"JVM doc status entry must be an object for {symbol}: {path}")
        status = payload.get("status")
        if not isinstance(status, str) or status not in JVM_DOC_OBJECT_STATUSES:
            allowed = ", ".join(sorted(JVM_DOC_OBJECT_STATUSES))
            raise ValueError(
                f"JVM doc status for {symbol} must be one of {allowed}: {path}"
            )
        statuses[symbol] = status

    return statuses


def load_jvm_doc_sources(
    manifest_path: Path,
    *,
    fixture_root: Path | None = None,
    include_versions: set[str] | None = None,
) -> list[JvmDocArtifactSource]:
    manifest = load_jvm_doc_manifest(manifest_path)
    root = fixture_root or manifest_path.parent
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("JVM doc manifest must include an `artifacts` list")

    artifact_sources: list[JvmDocArtifactSource] = []
    for entry in artifacts:
        if not isinstance(entry, dict):
            continue

        group = entry.get("group")
        artifact = entry.get("artifact")
        language = entry.get("language")
        versions = entry.get("versions")
        include_prefixes = entry.get("include_prefixes")
        status_manifest = entry.get("status_manifest")
        if not isinstance(group, str) or not group:
            continue
        if not isinstance(artifact, str) or not artifact:
            continue
        if not isinstance(language, str) or language not in {"java", "scala"}:
            continue
        if not isinstance(versions, list):
            continue
        if not isinstance(include_prefixes, list):
            include_prefixes = []

        version_sources: list[JvmDocVersionSource] = []
        for version_entry in versions:
            if not isinstance(version_entry, dict):
                continue
            version = version_entry.get("version")
            jar_path = version_entry.get("jar_path")
            if not isinstance(version, str) or not version:
                continue
            if include_versions is not None and version not in include_versions:
                continue
            if not isinstance(jar_path, str) or not jar_path:
                continue
            version_sources.append(
                JvmDocVersionSource(
                    version=version,
                    jar_path=str((root / jar_path).resolve()),
                )
            )

        if not version_sources:
            continue

        type_statuses: dict[str, str] = {}
        if isinstance(status_manifest, str) and status_manifest:
            type_statuses = load_jvm_doc_status_manifest((root / status_manifest).resolve())

        version_sources.sort(key=lambda source: version_key(source.version))
        artifact_sources.append(
            JvmDocArtifactSource(
                group=group,
                artifact=artifact,
                language=language,
                include_prefixes=[str(prefix) for prefix in include_prefixes if isinstance(prefix, str)],
                versions=version_sources,
                type_statuses=type_statuses,
            )
        )

    artifact_sources.sort(key=lambda source: (source.group, source.artifact, source.language))
    return artifact_sources
