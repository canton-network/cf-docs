from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def docs_json_page_ref(path: Path, docs_json_path: Path) -> str:
    relative = path.resolve().relative_to(docs_json_path.resolve().parent)
    if relative.suffix != ".mdx":
        raise ValueError(f"Expected MDX file under docs root, got: {path}")
    return relative.with_suffix("").as_posix()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def slugify(value: str) -> str:
    output = value.lower()
    output = re.sub(r"[^a-z0-9]+", "-", output)
    output = re.sub(r"-{2,}", "-", output).strip("-")
    return output or "item"


def mdx_title(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'^title:\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    if match:
        return match.group(1)
    match = re.search(r"^title:\s*'([^']+)'\s*$", text, flags=re.MULTILINE)
    if match:
        return match.group(1)
    match = re.search(r"^title:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return path.stem


def _protobuf_service_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"<dt>Service</dt>\s*<dd>([^<]+)</dd>", text)
    if match:
        return match.group(1)
    return path.parent.name


def _asyncapi_channel_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"<dt>Channel</dt>\s*<dd>([^<]+)</dd>", text)
    if match:
        return match.group(1)
    match = re.search(r'<h1 class="x2mdx-ref-title">([^<]+)</h1>', text)
    if match:
        return match.group(1)
    return mdx_title(path)


def build_asyncapi_nav_group(
    *,
    output_dir: Path,
    docs_json_path: Path,
    group_label: str,
) -> dict[str, Any]:
    pages: list[Any] = []
    channel_groups: list[Any] = []
    operation_root = output_dir / "operations"
    for channel_details_page in sorted(operation_root.glob("*/details.mdx"), key=lambda path: path.parent.name):
        channel_slug = channel_details_page.parent.name
        operation_dir = output_dir / "operations" / channel_slug
        operation_refs = [
            docs_json_page_ref(path, docs_json_path)
            for path in sorted(
                operation_dir.glob("*.mdx"),
                key=lambda path: (path.name == "details.mdx", mdx_title(path)),
            )
        ]
        channel_groups.append(
            {
                "group": _asyncapi_channel_name(channel_details_page),
                "pages": operation_refs,
            }
        )
    pages.extend(channel_groups)
    details_page = operation_root / "details.mdx"
    if details_page.exists():
        pages.append(docs_json_page_ref(details_page, docs_json_path))
    return {"group": group_label, "pages": pages}


def build_openrpc_nav_group(
    *,
    output_dir: Path,
    docs_json_path: Path,
    group_label: str,
    spec_ids: list[str],
    spec_dir_name: str = "specs",
    spec_group_sections: dict[str, str] | None = None,
) -> dict[str, Any]:
    pages: list[Any] = []
    section_pages: dict[str, list[Any]] = {}
    for spec_id in spec_ids:
        spec_page = output_dir / spec_dir_name / f"{slugify(spec_id)}.mdx"
        if not spec_page.exists():
            continue
        spec_page_ref = docs_json_page_ref(spec_page, docs_json_path)
        operation_dir = output_dir / "operations" / slugify(spec_id)
        operation_refs = [
            docs_json_page_ref(path, docs_json_path)
            for path in sorted(operation_dir.glob("*.mdx"), key=mdx_title)
            if path.name != "details.mdx"
        ]
        details_page = operation_dir / "details.mdx"
        if details_page.exists():
            operation_refs.append(docs_json_page_ref(details_page, docs_json_path))
        section = spec_group_sections.get(spec_id) if spec_group_sections else None
        if section:
            section_pages.setdefault(section, []).append(
                {
                    "group": mdx_title(spec_page),
                    "pages": [spec_page_ref, *operation_refs],
                }
            )
        else:
            pages.append(
                {
                    "group": mdx_title(spec_page),
                    "pages": [spec_page_ref, *operation_refs],
                }
            )
    if spec_group_sections:
        for section in dict.fromkeys(spec_group_sections[spec_id] for spec_id in spec_ids if spec_id in spec_group_sections):
            grouped_pages = section_pages.get(section)
            if grouped_pages:
                pages.append({"group": section, "pages": grouped_pages})
    details_page = output_dir / "operations" / "details.mdx"
    if details_page.exists():
        pages.append(docs_json_page_ref(details_page, docs_json_path))
    return {"group": group_label, "pages": pages}


def build_protobuf_nav_group(
    *,
    output_dir: Path,
    docs_json_path: Path,
    group_label: str,
    extra_page_refs: list[str] | None = None,
    include_details_page: bool = True,
) -> dict[str, Any]:
    details_page_ref = docs_json_page_ref(output_dir / "index.mdx", docs_json_path)
    pages: list[Any] = []
    package_groups: list[Any] = []
    for package_page in sorted((output_dir / "packages").glob("*.mdx"), key=mdx_title):
        package_slug = package_page.stem
        package_pages: list[Any] = [docs_json_page_ref(package_page, docs_json_path)]
        operation_root = output_dir / "operations" / package_slug
        service_groups: list[Any] = []
        if not operation_root.is_dir():
            package_groups.append({"group": mdx_title(package_page), "pages": package_pages})
            continue
        service_dirs = sorted(
            (path for path in operation_root.iterdir() if path.is_dir()),
            key=lambda path: path.name,
        )
        for service_dir in service_dirs:
            operation_pages = sorted(service_dir.glob("*.mdx"), key=mdx_title)
            if not operation_pages:
                continue
            service_groups.append(
                {
                    "group": _protobuf_service_name(operation_pages[0]),
                    "pages": [docs_json_page_ref(path, docs_json_path) for path in operation_pages],
                }
            )
        if service_groups:
            package_pages.append({"group": "Services", "pages": service_groups})
        package_groups.append({"group": mdx_title(package_page), "pages": package_pages})
    if package_groups:
        pages.append({"group": "Packages", "pages": package_groups})
    details_refs = [details_page_ref] if include_details_page else []
    for page_ref in [*(extra_page_refs or []), *details_refs]:
        if page_ref not in pages:
            pages.append(page_ref)
    return {"group": group_label, "pages": pages}


def replace_group_in_dropdown(*, docs_json_path: Path, dropdown_label: str, group: dict[str, Any]) -> None:
    payload = load_json(docs_json_path)
    navigation = payload.get("navigation")
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

    if not _replace_group(pages, group):
        pages.append(group)
    docs_json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _replace_group(items: list[Any], group: dict[str, Any]) -> bool:
    label = group.get("group")
    replaced = False
    for index, item in enumerate(list(items)):
        if isinstance(item, dict) and item.get("group") == label:
            items[index] = group
            replaced = True
        elif isinstance(item, dict):
            nested = item.get("pages")
            if isinstance(nested, list):
                replaced = _replace_group(nested, group) or replaced
    return replaced
