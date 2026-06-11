"""Models for versioned Daml docs JSON inputs and rendered reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from x2mdx.types import JsonValue


class DamlJsonModule(TypedDict, total=False):
    md_name: str
    md_anchor: str
    md_descr: JsonValue
    md_warn: JsonValue
    md_adts: list[JsonValue]
    md_classes: list[JsonValue]
    md_functions: list[JsonValue]
    md_interfaces: list[JsonValue]
    md_templates: list[JsonValue]
    md_instances: list[JsonValue]


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
