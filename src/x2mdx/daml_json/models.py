"""Models for versioned Daml docs JSON inputs and rendered reports."""

from __future__ import annotations

from dataclasses import dataclass

from x2mdx.types import JsonObject

DamlJsonModule = JsonObject


@dataclass(frozen=True)
class DamlDocsSnapshot:
    version: str
    json_path: str
    modules: list[DamlJsonModule]


@dataclass(frozen=True)
class DamlDocsSources:
    snapshots: list[DamlDocsSnapshot]
    publish_version: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class DamlDocsReport:
    source_name: str
    version_filter: str
    publish_version: str
    versions: list[str]
    modules: list[DamlJsonModule]
    module_lifecycle: dict[str, dict[str, str | None]]
    module_deprecation_first_seen: dict[str, str]
