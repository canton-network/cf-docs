"""Models for versioned TypeDoc JSON inputs and rendered reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from x2mdx.types import JsonValue


class TypeDocDocument(TypedDict, total=False):
    packageName: str
    name: str
    groups: list[JsonValue]
    children: list[JsonValue]


class TypeDocChangeDetail(TypedDict):
    version: str
    changes: list[str]


class TypeDocExport(TypedDict):
    name: str
    anchor: str
    group: str
    kind_label: str
    summary: str
    signature: str
    type_parameters: list[JsonValue]
    signature_docs: list[JsonValue]
    members: list[JsonValue]
    lifecycle_state: str | None
    lifecycle_label: str | None
    replaces: str | None
    deprecated_text: str | None
    source_location: str | None
    introduced_in: str
    removed_in: str | None
    status: str
    sort_item_index: int
    change_details: list[TypeDocChangeDetail]


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
