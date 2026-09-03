from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Required, TypedDict, cast

from generated_reference_sources.common import (
    SourceUpdate,
    load_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_KEY = "daml-standard-library"
SOURCE_LABEL = "Daml Standard Library"
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "daml-standard-library" / "source-artifacts.json"


class DamlStandardLibrarySourceConfigPayload(TypedDict, total=False):
    source: str
    min_version: Required[str]
    package_set: str
    sdk_source: str


@dataclass(frozen=True)
class DamlStandardLibrarySourceConfig:
    raw: DamlStandardLibrarySourceConfigPayload
    min_version: str


def parse_source_config(path: Path) -> DamlStandardLibrarySourceConfig:
    raw_json = load_json(path)
    min_version = raw_json.get("min_version")
    if not isinstance(min_version, str) or not min_version:
        raise ValueError(f"{path} must define non-empty min_version")
    raw = cast(DamlStandardLibrarySourceConfigPayload, raw_json)
    return DamlStandardLibrarySourceConfig(raw=raw, min_version=min_version)


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> SourceUpdate | None:
    del dry_run
    parse_source_config(source_config_path)
    return None
