"""Shared types for parsed reference-doc data structures."""

from __future__ import annotations

from typing import TypeAlias, TypedDict

JsonValue: TypeAlias = str | int | float | bool | None | dict[str, "JsonValue"] | list["JsonValue"]


class MintlifyNavGroup(TypedDict, total=False):
    group: str
    pages: "MintlifyNavItems"
    groups: "MintlifyNavItems"
    expanded: bool
    openapi: str
    asyncapi: str


MintlifyNavItem: TypeAlias = str | MintlifyNavGroup
MintlifyNavItems: TypeAlias = list[MintlifyNavItem]


def require_json_value(value: object, *, path: str = "$") -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [require_json_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        output: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"Expected string key at {path}, got {type(key).__name__}")
            output[key] = require_json_value(item, path=f"{path}.{key}")
        return output
    raise ValueError(f"Expected JSON-compatible value at {path}, got {type(value).__name__}")


def require_json_object(value: object, *, path: str = "$") -> dict[str, JsonValue]:
    json_value = require_json_value(value, path=path)
    if not isinstance(json_value, dict):
        raise ValueError(f"Expected JSON object at {path}, got {type(json_value).__name__}")
    return json_value


def require_json_array(value: object, *, path: str = "$") -> list[JsonValue]:
    json_value = require_json_value(value, path=path)
    if not isinstance(json_value, list):
        raise ValueError(f"Expected JSON array at {path}, got {type(json_value).__name__}")
    return json_value


def require_mintlify_nav_items(value: object, *, path: str = "$") -> MintlifyNavItems:
    if not isinstance(value, list):
        raise ValueError(f"Expected Mintlify nav items list at {path}, got {type(value).__name__}")
    for index, item in enumerate(value):
        require_mintlify_nav_item(item, path=f"{path}[{index}]")
    return value


def require_mintlify_nav_item(value: object, *, path: str = "$") -> None:
    if isinstance(value, str):
        return
    if not isinstance(value, dict):
        raise ValueError(f"Expected Mintlify nav string or group at {path}, got {type(value).__name__}")

    group = value.get("group")
    if group is not None and not isinstance(group, str):
        raise ValueError(f"Expected Mintlify group label string at {path}.group")
    for key in ("pages", "groups"):
        nested = value.get(key)
        if nested is not None:
            require_mintlify_nav_items(nested, path=f"{path}.{key}")
    expanded = value.get("expanded")
    if expanded is not None and not isinstance(expanded, bool):
        raise ValueError(f"Expected Mintlify expanded flag boolean at {path}.expanded")
    for key in ("openapi", "asyncapi"):
        spec_path = value.get(key)
        if spec_path is not None and not isinstance(spec_path, str):
            raise ValueError(f"Expected Mintlify {key} path string at {path}.{key}")
