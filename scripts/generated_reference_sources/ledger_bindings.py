from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from generated_reference_sources.common import SourceUpdate, load_json, write_json


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_KEY = "ledger-bindings"
SOURCE_LABEL = "Java ledger bindings"
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "ledger-bindings" / "source-artifacts.json"
DEFAULT_TIMEOUT_SECONDS = 20.0
USER_AGENT = "cf-docs-generated-reference-source-updater"
STABLE_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class LedgerBindingArtifactConfig:
    raw: dict[str, object]
    group: str
    artifact: str
    language: str
    versions: tuple[str, ...]


@dataclass(frozen=True)
class LedgerBindingsSourceConfig:
    raw: dict[str, object]
    repo_base: str
    artifacts: tuple[LedgerBindingArtifactConfig, ...]


def parse_source_config(path: Path) -> LedgerBindingsSourceConfig:
    raw_json = load_json(path)
    repo_base = raw_json.get("repo_base")
    artifacts_json = raw_json.get("artifacts")
    if not isinstance(repo_base, str) or not repo_base:
        raise ValueError(f"{path} must define non-empty repo_base")
    if not isinstance(artifacts_json, list) or not artifacts_json:
        raise ValueError(f"{path} must define a non-empty artifacts list")

    artifacts: list[LedgerBindingArtifactConfig] = []
    for index, artifact_json in enumerate(artifacts_json):
        if not isinstance(artifact_json, dict):
            raise ValueError(f"{path} artifacts[{index}] must be an object")
        group = artifact_json.get("group")
        artifact = artifact_json.get("artifact")
        language = artifact_json.get("language")
        versions = artifact_json.get("versions")
        if not isinstance(group, str) or not group:
            raise ValueError(f"{path} artifacts[{index}] must define group")
        if not isinstance(artifact, str) or not artifact:
            raise ValueError(f"{path} artifacts[{index}] must define artifact")
        if not isinstance(language, str) or not language:
            raise ValueError(f"{path} artifacts[{group}:{artifact}] must define language")
        if not isinstance(versions, list) or not all(isinstance(version, str) and version for version in versions):
            raise ValueError(f"{path} artifacts[{group}:{artifact}] must define a non-empty versions string list")
        artifacts.append(
            LedgerBindingArtifactConfig(
                raw=dict(artifact_json),
                group=group,
                artifact=artifact,
                language=language,
                versions=tuple(versions),
            )
        )
    return LedgerBindingsSourceConfig(raw=raw_json, repo_base=repo_base, artifacts=tuple(artifacts))


def version_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return (int(major), int(minor), int(patch))


def metadata_url(repo_base: str, *, group: str, artifact: str) -> str:
    group_path = group.replace(".", "/")
    return f"{repo_base.rstrip('/')}/{group_path}/{artifact}/maven-metadata.xml"


def latest_maven_version(
    repo_base: str,
    *,
    group: str,
    artifact: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    request = urllib.request.Request(
        metadata_url(repo_base, group=group, artifact=artifact),
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    versions = [
        node.text.strip()
        for node in root.findall("./versioning/versions/version")
        if node.text and STABLE_VERSION_RE.fullmatch(node.text.strip())
    ]
    if not versions:
        raise ValueError(f"No stable Maven versions found for {group}:{artifact}")
    return sorted(versions, key=version_key)[-1]


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> list[SourceUpdate]:
    source_config = parse_source_config(source_config_path)
    updates: list[SourceUpdate] = []
    updated_artifacts: list[dict[str, Any]] = []

    for artifact in source_config.artifacts:
        current_version = latest_maven_version(
            source_config.repo_base,
            group=artifact.group,
            artifact=artifact.artifact,
        )
        updated_artifact = dict(artifact.raw)
        if current_version not in artifact.versions:
            updates.append(
                SourceUpdate(
                    source=f"{SOURCE_LABEL} {artifact.group}:{artifact.artifact}",
                    path=source_config_path,
                    field="versions",
                    previous=", ".join(artifact.versions),
                    current=current_version,
                )
            )
            updated_artifact["versions"] = [*artifact.versions, current_version]
        updated_artifacts.append(updated_artifact)

    if updates and not dry_run:
        updated_config = dict(source_config.raw)
        updated_config["artifacts"] = updated_artifacts
        write_json(source_config_path, updated_config)
    return updates
