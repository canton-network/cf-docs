from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Required, TypedDict

import generate_splice_mintlify_openapi as splice_openapi_generator

from generated_reference_sources.common import SourceUpdate, load_json, write_json


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_KEY = "splice-openapi"
SOURCE_LABEL = "Splice OpenAPI"
DEFAULT_SOURCE_CONFIG = (
    REPO_ROOT / "config" / "mintlify-openapi" / "splice-openapi" / "source-artifacts.json"
)


class SpliceOpenApiSpecConfig(TypedDict, total=False):
    filename: str
    nav_label: str
    source: str
    directory: str


class SpliceOpenApiFamilyConfig(TypedDict, total=False):
    group: str
    specs: list[SpliceOpenApiSpecConfig]


class SpliceOpenApiSourceConfigPayload(TypedDict, total=False):
    source: str
    release_repo: str
    tag_regex: str
    min_version: str
    publish_version: Required[str]
    asset_template: str
    nav_dropdown: str
    top_level_group_label: str
    insert_after_group: str
    managed_openapi_root: str
    enabled_nav_specs: list[str]
    legacy_cleanup_paths: list[str]
    families: list[SpliceOpenApiFamilyConfig]


@dataclass(frozen=True)
class SpliceOpenApiSourceConfig:
    raw: SpliceOpenApiSourceConfigPayload
    publish_version: str


def parse_source_config(path: Path) -> SpliceOpenApiSourceConfig:
    raw_json = load_json(path)
    publish_version = raw_json.get("publish_version")
    if not isinstance(publish_version, str) or not publish_version:
        raise ValueError(f"{path} must define non-empty publish_version")
    raw: SpliceOpenApiSourceConfigPayload = {}
    raw.update(raw_json)
    return SpliceOpenApiSourceConfig(raw=raw, publish_version=publish_version)


def latest_version(source_config: SpliceOpenApiSourceConfig) -> str:
    releases = splice_openapi_generator.selected_releases(
        source_config=source_config.raw,
        include_versions=None,
    )
    return releases[-1]["version"]


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> SourceUpdate | None:
    source_config = parse_source_config(source_config_path)
    current_version = latest_version(source_config)
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
        updated_config["publish_version"] = current_version
        write_json(source_config_path, updated_config)
    return update
