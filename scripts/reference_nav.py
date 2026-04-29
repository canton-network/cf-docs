from __future__ import annotations

import json
from pathlib import Path
from typing import Any


LEDGER_API_PARENT_GROUP = "Ledger API"
LEGACY_ENDPOINTS_GROUP = "Ledger API Endpoints"
OPENAPI_GROUP = "OpenAPI"
ASYNCAPI_GROUP = "AsyncAPI"
GRPC_GROUP = "gRPC Ledger API Reference"
PROTOBUF_GROUP = "Protobufs"
PROTOBUF_GROUP_ALIASES = {"Canton Protobuf", "Canton Protobuf History", PROTOBUF_GROUP}
BINDINGS_GROUP = "Ledger API Java Bindings"
BINDINGS_GROUP_ALIASES = {BINDINGS_GROUP, "Ledger API JVM Bindings"}
LEDGER_API_CHILD_ORDER = [
    OPENAPI_GROUP,
    ASYNCAPI_GROUP,
    GRPC_GROUP,
    PROTOBUF_GROUP,
    BINDINGS_GROUP,
]
OPENAPI_PAGE_REF = "reference/json-api-reference"
ASYNCAPI_PAGE_REF = "reference/json-api-asyncapi-reference/index"
GRPC_OVERVIEW_PAGE_REF = "reference/grpc-ledger-api-reference/index"
GRPC_PACKAGES_PREFIX = "reference/grpc-ledger-api-reference/packages/"
PROTOBUF_OVERVIEW_PAGE_REF = "reference/protobuf/index"
BINDINGS_OVERVIEW_PAGE_REF = "reference/ledger-api-jvm-bindings"
LANGUAGE_GROUPS = {"Scaladocs", "Javadocs"}
SCALADOC_PREFIX = "reference/scala/"
JAVADOC_PREFIX = "reference/java/"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _find_group(items: list[Any], label: str) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and item.get("group") == label:
            return item
    return None


def _merge_group_entries(target: dict[str, Any], source: dict[str, Any]) -> None:
    for spec_key in ("openapi", "asyncapi"):
        if spec_key in source:
            target[spec_key] = source[spec_key]

    source_pages = source.get("pages")
    if source_pages is None:
        return
    if not isinstance(source_pages, list):
        return

    target_pages = target.get("pages")
    if target_pages is None:
        target_pages = []
        target["pages"] = target_pages
    elif not isinstance(target_pages, list):
        target_pages = []
        target["pages"] = target_pages

    for item in source_pages:
        if isinstance(item, str):
            if item not in target_pages:
                target_pages.append(item)
            continue
        if isinstance(item, dict):
            label = item.get("group")
            if isinstance(label, str) and label:
                existing = _find_group(target_pages, label)
                if existing is None:
                    target_pages.append(item)
                else:
                    _merge_group_entries(existing, item)
                continue
        target_pages.append(item)


def _upsert_group(collected: dict[str, dict[str, Any]], label: str) -> dict[str, Any]:
    group = collected.get(label)
    if group is None:
        group = {"group": label}
        collected[label] = group
    return group


def _append_unique(items: list[str], values: list[str]) -> None:
    for value in values:
        if value not in items:
            items.append(value)


def _absorb_known_item(item: Any, collected: dict[str, dict[str, Any]]) -> bool:
    if isinstance(item, str):
        if item == OPENAPI_PAGE_REF:
            _merge_group_entries(_upsert_group(collected, OPENAPI_GROUP), {"group": OPENAPI_GROUP, "pages": [item]})
            return True
        elif item == ASYNCAPI_PAGE_REF:
            _merge_group_entries(_upsert_group(collected, ASYNCAPI_GROUP), {"group": ASYNCAPI_GROUP, "pages": [item]})
            return True
        elif item == GRPC_OVERVIEW_PAGE_REF:
            _merge_group_entries(_upsert_group(collected, GRPC_GROUP), {"group": GRPC_GROUP, "pages": [item]})
            return True
        elif item.startswith(GRPC_PACKAGES_PREFIX):
            _merge_group_entries(
                _upsert_group(collected, GRPC_GROUP),
                {"group": GRPC_GROUP, "pages": [{"group": "Packages", "pages": [item]}]},
            )
            return True
        elif item == PROTOBUF_OVERVIEW_PAGE_REF:
            _merge_group_entries(_upsert_group(collected, PROTOBUF_GROUP), {"group": PROTOBUF_GROUP, "pages": [item]})
            return True
        elif item == BINDINGS_OVERVIEW_PAGE_REF:
            _merge_group_entries(_upsert_group(collected, BINDINGS_GROUP), {"group": BINDINGS_GROUP, "pages": [item]})
            return True
        elif item.startswith(SCALADOC_PREFIX):
            _merge_group_entries(
                _upsert_group(collected, BINDINGS_GROUP),
                {"group": BINDINGS_GROUP, "pages": [{"group": "Scaladocs", "pages": [item]}]},
            )
            return True
        elif item.startswith(JAVADOC_PREFIX):
            _merge_group_entries(
                _upsert_group(collected, BINDINGS_GROUP),
                {"group": BINDINGS_GROUP, "pages": [{"group": "Javadocs", "pages": [item]}]},
            )
            return True
        return False

    if not isinstance(item, dict):
        return False

    label = item.get("group")
    if not isinstance(label, str) or not label:
        return False

    if label == LEDGER_API_PARENT_GROUP:
        absorbed = False
        nested_pages = item.get("pages")
        if isinstance(nested_pages, list):
            for nested in nested_pages:
                absorbed = _absorb_known_item(nested, collected) or absorbed
        return absorbed

    if label == LEGACY_ENDPOINTS_GROUP:
        absorbed = False
        pages = item.get("pages")
        if isinstance(pages, list):
            for page_ref in pages:
                absorbed = _absorb_known_item(page_ref, collected) or absorbed
        return absorbed

    if label in {OPENAPI_GROUP, ASYNCAPI_GROUP, GRPC_GROUP}:
        _merge_group_entries(_upsert_group(collected, label), item)
        return True

    if label in PROTOBUF_GROUP_ALIASES:
        normalized = {"group": PROTOBUF_GROUP, "pages": []}
        _merge_group_entries(normalized, item)
        _merge_group_entries(_upsert_group(collected, PROTOBUF_GROUP), normalized)
        return True

    if label in BINDINGS_GROUP_ALIASES:
        normalized = {"group": BINDINGS_GROUP, "pages": []}
        _merge_group_entries(normalized, item)
        _merge_group_entries(_upsert_group(collected, BINDINGS_GROUP), normalized)
        return True

    if label == "Packages":
        pages = item.get("pages")
        if isinstance(pages, list) and all(isinstance(page, str) and page.startswith(GRPC_PACKAGES_PREFIX) for page in pages):
            _merge_group_entries(_upsert_group(collected, GRPC_GROUP), {"group": GRPC_GROUP, "pages": [item]})
            return True

    if label in LANGUAGE_GROUPS:
        _merge_group_entries(_upsert_group(collected, BINDINGS_GROUP), {"group": BINDINGS_GROUP, "pages": [item]})
        return True

    return False


def regroup_ledger_api_nav(*, docs_json_path: Path, dropdown_label: str) -> None:
    docs = load_json(docs_json_path)
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

    known_labels = {
        LEDGER_API_PARENT_GROUP,
        LEGACY_ENDPOINTS_GROUP,
        GRPC_GROUP,
        *PROTOBUF_GROUP_ALIASES,
        *BINDINGS_GROUP_ALIASES,
    }
    collected: dict[str, dict[str, Any]] = {}
    preserved_ledger_children: list[Any] = []
    remaining: list[Any] = []
    insert_at: int | None = None

    for index, item in enumerate(pages):
        if isinstance(item, dict) and item.get("group") == LEDGER_API_PARENT_GROUP:
            if insert_at is None:
                insert_at = index
            nested_pages = item.get("pages")
            if isinstance(nested_pages, list):
                for nested in nested_pages:
                    if not _absorb_known_item(nested, collected):
                        preserved_ledger_children.append(nested)
            continue
        if isinstance(item, dict) and item.get("group") in known_labels:
            if insert_at is None:
                insert_at = index
            _absorb_known_item(item, collected)
            continue
        remaining.append(item)

    if not collected:
        return

    parent_group = {
        "group": LEDGER_API_PARENT_GROUP,
        "pages": [
            *preserved_ledger_children,
            *[collected[label] for label in LEDGER_API_CHILD_ORDER if label in collected],
        ],
    }

    if insert_at is None:
        remaining.append(parent_group)
    else:
        remaining.insert(min(insert_at, len(remaining)), parent_group)

    dropdown["pages"] = remaining
    docs_json_path.write_text(json.dumps(docs, indent=2) + "\n", encoding="utf-8")
