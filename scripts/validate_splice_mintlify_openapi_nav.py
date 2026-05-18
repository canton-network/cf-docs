#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "mintlify-openapi" / "splice-openapi" / "source-artifacts.json"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def navigation_dropdown_pages(docs: dict[str, Any], dropdown_label: str, docs_json_path: Path) -> list[Any]:
    navigation = docs.get("navigation")
    if not isinstance(navigation, dict):
        raise ValueError(f"docs.json missing navigation object: {docs_json_path}")
    dropdowns = navigation.get("dropdowns")
    if not isinstance(dropdowns, list):
        raise ValueError(f"docs.json navigation.dropdowns must be a list: {docs_json_path}")
    dropdown = next(
        (item for item in dropdowns if isinstance(item, dict) and item.get("dropdown") == dropdown_label),
        None,
    )
    if dropdown is None:
        raise ValueError(f"Dropdown not found in docs.json: {dropdown_label}")
    pages = dropdown.get("pages")
    if not isinstance(pages, list):
        raise ValueError(f"Dropdown does not expose a pages list: {dropdown_label}")
    return pages


def find_group(items: list[Any], label: str) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and item.get("group") == label:
            return item
    return None


def enabled_specs(source_config: dict[str, Any]) -> set[str] | None:
    enabled = source_config.get("enabled_nav_specs")
    if enabled is None:
        return None
    if not isinstance(enabled, list):
        raise ValueError("enabled_nav_specs must be a list when set")
    specs: set[str] = set()
    for item in enabled:
        if not isinstance(item, str) or not item:
            raise ValueError("enabled_nav_specs entries must be non-empty strings")
        specs.add(item)
    return specs


def expected_openapi_specs(source_config: dict[str, Any]) -> list[dict[str, Any]]:
    selected = enabled_specs(source_config)
    families = source_config.get("families")
    if not isinstance(families, list):
        raise ValueError("Source config must define families")
    entries: list[dict[str, Any]] = []
    for family in families:
        if not isinstance(family, dict):
            raise ValueError("Each source config family must be an object")
        family_group = family.get("group")
        specs = family.get("specs")
        if not isinstance(family_group, str) or not family_group:
            raise ValueError("Each source config family must define group")
        if not isinstance(specs, list):
            raise ValueError("Each source config family must define specs")
        for spec in specs:
            if not isinstance(spec, dict):
                raise ValueError("Each source config spec must be an object")
            filename = spec.get("filename")
            nav_label = spec.get("nav_label")
            source = spec.get("source")
            directory = spec.get("directory")
            if not all(isinstance(item, str) and item for item in (filename, nav_label, source, directory)):
                raise ValueError("Each source config spec must define filename, nav_label, source, and directory")
            if selected is None or filename in selected:
                entries.append(
                    {
                        "family_group": family_group,
                        "filename": filename,
                        "nav_label": nav_label,
                        "source": source,
                        "directory": directory,
                    }
                )
    return entries


def expected_openapi_entries(source_config: dict[str, Any]) -> list[tuple[str, str]]:
    return [(spec["source"], spec["directory"]) for spec in expected_openapi_specs(source_config)]


def collect_openapi_entries(node: Any, entries: set[tuple[str, str]]) -> None:
    if isinstance(node, list):
        for item in node:
            collect_openapi_entries(item, entries)
        return
    if not isinstance(node, dict):
        return
    openapi = node.get("openapi")
    if isinstance(openapi, dict):
        source = openapi.get("source")
        directory = openapi.get("directory")
        if isinstance(source, str) and isinstance(directory, str):
            entries.add((source, directory))
    pages = node.get("pages")
    if isinstance(pages, list):
        collect_openapi_entries(pages, entries)


def openapi_operations_without_summary(openapi_path: Path) -> list[str]:
    spec = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError(f"Expected OpenAPI spec to parse as an object: {openapi_path}")
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return []

    missing: list[str] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            summary = operation.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                missing.append(f"{method.upper()} {path}")
    return missing


def openapi_operation_page_refs(openapi_path: Path) -> list[str]:
    spec = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError(f"Expected OpenAPI spec to parse as an object: {openapi_path}")
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return []

    refs: list[str] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            refs.append(f"{method.upper()} {path}")
    return refs


def validate_openapi_operation_summaries(
    *,
    docs_json_path: Path,
    entries: list[tuple[str, str]],
) -> None:
    failures: list[str] = []
    docs_root = docs_json_path.parent
    for source, _directory in entries:
        openapi_path = docs_root / source
        missing = openapi_operations_without_summary(openapi_path)
        failures.extend(f"{source}: {operation}" for operation in missing)

    if failures:
        details = "\n".join(f"- {failure}" for failure in failures)
        raise ValueError(
            "Splice OpenAPI specs contain operations without summaries; Mintlify uses summaries for readable TOC labels.\n"
            f"{details}"
        )


def validate_explicit_openapi_nav_pages(
    *,
    docs_json_path: Path,
    top_group: dict[str, Any],
    expected_specs: list[dict[str, Any]],
) -> None:
    docs_root = docs_json_path.parent
    top_group_pages = top_group.get("pages")
    if not isinstance(top_group_pages, list):
        raise ValueError("Configured Splice OpenAPI top-level group must expose pages")

    for spec in expected_specs:
        family_group = find_group(top_group_pages, spec["family_group"])
        if family_group is None:
            raise ValueError(f"Splice OpenAPI family is missing from nav: {spec['family_group']}")
        family_pages = family_group.get("pages")
        if not isinstance(family_pages, list):
            raise ValueError(f"Splice OpenAPI family must expose pages: {spec['family_group']}")
        spec_group = find_group(family_pages, spec["nav_label"])
        if spec_group is None:
            raise ValueError(f"Splice OpenAPI spec is missing from nav: {spec['nav_label']}")
        actual_pages = spec_group.get("pages")
        if not isinstance(actual_pages, list):
            raise ValueError(f"Splice OpenAPI spec must expose explicit pages: {spec['nav_label']}")
        expected_pages = openapi_operation_page_refs(docs_root / spec["source"])
        if actual_pages != expected_pages:
            raise ValueError(
                f"Splice OpenAPI nav pages differ for {spec['nav_label']}:\n"
                f"expected={expected_pages}\nactual={actual_pages}"
            )


def validate_splice_nav(*, source_config_path: Path = DEFAULT_SOURCE_CONFIG, docs_json_path: Path = DEFAULT_DOCS_JSON) -> None:
    source_config = load_json(source_config_path)
    docs = load_json(docs_json_path)
    dropdown_label = source_config.get("nav_dropdown") or "API Reference"
    if not isinstance(dropdown_label, str):
        raise ValueError("nav_dropdown must be a string")
    top_level_group_label = source_config.get("top_level_group_label") or "Splice APIs"
    if not isinstance(top_level_group_label, str):
        raise ValueError("top_level_group_label must be a string")

    pages = navigation_dropdown_pages(docs, dropdown_label, docs_json_path)
    top_group = find_group(pages, top_level_group_label)
    if top_group is None:
        raise ValueError(f"Configured Splice OpenAPI nav group is missing: {top_level_group_label}")

    actual_entries: set[tuple[str, str]] = set()
    collect_openapi_entries(top_group, actual_entries)
    expected_specs = expected_openapi_specs(source_config)
    expected_entries = [(spec["source"], spec["directory"]) for spec in expected_specs]
    missing = [entry for entry in expected_entries if entry not in actual_entries]
    if missing:
        details = "\n".join(f"- source={source} directory={directory}" for source, directory in missing)
        raise ValueError(f"Splice OpenAPI nav is missing configured entries:\n{details}")
    validate_openapi_operation_summaries(docs_json_path=docs_json_path, entries=expected_entries)
    validate_explicit_openapi_nav_pages(
        docs_json_path=docs_json_path,
        top_group=top_group,
        expected_specs=expected_specs,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate configured Splice OpenAPI specs are wired into docs.json.")
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validate_splice_nav(
        source_config_path=Path(args.source_config).resolve(),
        docs_json_path=Path(args.docs_json).resolve(),
    )
    print("Validated Splice OpenAPI navigation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
