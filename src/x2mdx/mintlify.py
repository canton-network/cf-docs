"""Helpers for writing simple Mintlify preview sites."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from x2mdx.output import Page
from x2mdx.render import write_pages


@dataclass(frozen=True)
class MintlifyGroup:
    group: str
    pages: list[Any]
    expanded: bool | None = None


@dataclass(frozen=True)
class MintlifyNavTarget:
    dropdown: str
    groups: list[str]
    versions: list[str] | None = None


def _group_to_json(group: MintlifyGroup) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "group": group.group,
        "pages": [
            _group_to_json(item) if isinstance(item, MintlifyGroup) else item
            for item in group.pages
        ],
    }
    if group.expanded is not None:
        payload["expanded"] = group.expanded
    return payload


def write_docs_json(
    root: Path,
    *,
    site_name: str,
    groups: list[MintlifyGroup],
    colors: dict[str, str] | None = None,
) -> Path:
    docs_json = {
        "$schema": "https://mintlify.com/docs.json",
        "name": site_name,
        "theme": "mint",
        "colors": colors
        or {
            "primary": "#0A5BC2",
            "light": "#0A5BC2",
            "dark": "#0A5BC2",
        },
        "navigation": {
            "groups": [_group_to_json(group) for group in groups],
        },
    }
    target = root / "docs.json"
    target.write_text(json.dumps(docs_json, indent=2) + "\n", encoding="utf-8")
    return target


def _remove_page_reference(node: Any, page_ref: str) -> None:
    if isinstance(node, dict):
        pages = node.get("pages")
        if isinstance(pages, list):
            node["pages"] = [item for item in pages if item != page_ref]
            for item in node["pages"]:
                _remove_page_reference(item, page_ref)
        for value in node.values():
            if value is not pages:
                _remove_page_reference(value, page_ref)
    elif isinstance(node, list):
        for item in node:
            _remove_page_reference(item, page_ref)


def _find_group(groups: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    for item in groups:
        if isinstance(item, dict) and item.get("group") == label:
            return item
    return None


def _ensure_group_path(container: dict[str, Any], group_path: list[str]) -> list[Any]:
    if not group_path:
        return container.setdefault("pages", [])

    current_groups = container.setdefault("groups", [])
    current: dict[str, Any] | None = None
    for index, label in enumerate(group_path):
        current = _find_group(current_groups, label)
        if current is None:
            current = {"group": label, "pages": []}
            current_groups.append(current)
        if index < len(group_path) - 1:
            current_groups = current.setdefault("groups", [])
    return current.setdefault("pages", []) if current is not None else container.setdefault("pages", [])


def _prune_empty_groups(node: Any) -> None:
    if isinstance(node, dict):
        for value in list(node.values()):
            _prune_empty_groups(value)
        if node.get("groups") == []:
            node.pop("groups")
    elif isinstance(node, list):
        for item in node:
            _prune_empty_groups(item)


def docs_json_page_ref(output_file: Path, docs_json_path: Path) -> str:
    try:
        relative = output_file.resolve().relative_to(docs_json_path.resolve().parent)
    except ValueError as exc:
        raise ValueError("Output file must live under the docs.json directory") from exc

    if relative.suffix != ".mdx":
        raise ValueError("Output file must end with .mdx to be referenced from docs.json")
    return relative.with_suffix("").as_posix()


def update_docs_json_navigation(
    docs_json_path: Path,
    *,
    output_file: Path,
    target: MintlifyNavTarget,
) -> Path:
    docs = json.loads(docs_json_path.read_text(encoding="utf-8"))
    page_ref = docs_json_page_ref(output_file, docs_json_path)
    navigation = docs.setdefault("navigation", {})
    nav_section = None
    dropdowns = navigation.get("dropdowns")
    if isinstance(dropdowns, list):
        nav_section = next(
            (item for item in dropdowns if isinstance(item, dict) and item.get("dropdown") == target.dropdown),
            None,
        )
    products = navigation.get("products")
    if nav_section is None and isinstance(products, list):
        nav_section = next(
            (item for item in products if isinstance(item, dict) and item.get("product") == target.dropdown),
            None,
        )
    if nav_section is None:
        raise ValueError(f"Navigation section not found in docs.json: {target.dropdown}")

    _remove_page_reference(navigation, page_ref)

    versions = nav_section.get("versions")
    if isinstance(versions, list):
        version_names = target.versions or [
            item.get("version")
            for item in versions
            if isinstance(item, dict) and item.get("version")
        ]
        for version_name in version_names:
            version_entry = next(
                (item for item in versions if isinstance(item, dict) and item.get("version") == version_name),
                None,
            )
            if version_entry is None:
                raise ValueError(f"Version not found under navigation section {target.dropdown}: {version_name}")
            pages = _ensure_group_path(version_entry, target.groups)
            if page_ref not in pages:
                pages.append(page_ref)
    else:
        pages = _ensure_group_path(nav_section, target.groups)
        if page_ref not in pages:
            pages.append(page_ref)

    _prune_empty_groups(navigation)
    docs_json_path.write_text(json.dumps(docs, indent=2) + "\n", encoding="utf-8")
    return docs_json_path


def write_preview_site(
    root: Path,
    *,
    site_name: str,
    pages: list[Page],
    groups: list[MintlifyGroup],
) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    written = write_pages(pages, root)
    write_docs_json(root, site_name=site_name, groups=groups)
    return written
