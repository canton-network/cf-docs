"""Shared types for parsed reference-doc data structures."""

from __future__ import annotations

from typing import TypeAlias, TypedDict

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonObject: TypeAlias = dict[str, "JsonValue"]
JsonArray: TypeAlias = list["JsonValue"]
JsonValue: TypeAlias = JsonPrimitive | JsonObject | JsonArray

VersionSortPart: TypeAlias = int | str
VersionSortKey: TypeAlias = tuple[VersionSortPart, ...]


class MintlifyNavGroup(TypedDict, total=False):
    group: str
    pages: "MintlifyNavItems"
    groups: "MintlifyNavItems"
    expanded: bool
    openapi: str
    asyncapi: str


MintlifyNavItem: TypeAlias = str | MintlifyNavGroup
MintlifyNavItems: TypeAlias = list[MintlifyNavItem]
