from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Required, TypedDict

from generated_reference_sources.common import SourceUpdate, load_json, write_json


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_KEY = "daml-standard-library"
SOURCE_LABEL = "Daml Standard Library"
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "daml-standard-library" / "source-artifacts.json"
DEFAULT_TIMEOUT_SECONDS = 20.0
DPM_LATEST_URL = "https://get.digitalasset.com/install/latest"
USER_AGENT = "cf-docs-generated-reference-source-updater"


class DamlStandardLibrarySourceConfigPayload(TypedDict, total=False):
    source: str
    publish_version: Required[str]
    package_set: str
    sdk_source: str
    versions: Required[list[str]]


@dataclass(frozen=True)
class DamlStandardLibrarySourceConfig:
    raw: DamlStandardLibrarySourceConfigPayload
    publish_version: str
    versions: tuple[str, ...]


def parse_source_config(path: Path) -> DamlStandardLibrarySourceConfig:
    raw_json = load_json(path)
    publish_version = raw_json.get("publish_version")
    versions = raw_json.get("versions")
    if not isinstance(publish_version, str) or not publish_version:
        raise ValueError(f"{path} must define non-empty publish_version")
    if not isinstance(versions, list) or not all(isinstance(version, str) and version for version in versions):
        raise ValueError(f"{path} must define a non-empty versions string list")
    raw: DamlStandardLibrarySourceConfigPayload = {}
    raw.update(raw_json)
    return DamlStandardLibrarySourceConfig(raw=raw, publish_version=publish_version, versions=tuple(versions))


def latest_dpm_version(*, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    request = urllib.request.Request(DPM_LATEST_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        version = response.read().decode("utf-8").strip()
    if not version:
        raise ValueError(f"{DPM_LATEST_URL} returned an empty latest version")
    return version


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> SourceUpdate | None:
    source_config = parse_source_config(source_config_path)
    current_version = latest_dpm_version()
    if source_config.publish_version == current_version:
        return None

    update = SourceUpdate(
        source=SOURCE_LABEL,
        path=source_config_path,
        field="publish_version",
        previous=source_config.publish_version,
        current=current_version,
    )
    if not dry_run:
        updated_config = dict(source_config.raw)
        versions = list(source_config.versions)
        if current_version not in versions:
            versions.append(current_version)
        updated_config["publish_version"] = current_version
        updated_config["versions"] = versions
        write_json(source_config_path, updated_config)
    return update
