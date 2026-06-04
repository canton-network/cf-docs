"""Models for versioned TypeDoc JSON inputs and rendered reports."""

from __future__ import annotations

from dataclasses import dataclass

from x2mdx.types import JsonObject

TypeDocDocument = JsonObject
TypeDocExport = JsonObject


@dataclass(frozen=True)
class TypeDocSnapshot:
    version: str
    json_path: str
    document: TypeDocDocument


@dataclass(frozen=True)
class TypeDocSources:
    snapshots: list[TypeDocSnapshot]
    publish_version: str | None = None
    source: str | None = None
    package_name: str | None = None


@dataclass(frozen=True)
class TypeDocReport:
    source_name: str
    version_filter: str
    package_name: str
    publish_version: str
    versions: list[str]
    export_groups: list[str]
    exports: list[TypeDocExport]
