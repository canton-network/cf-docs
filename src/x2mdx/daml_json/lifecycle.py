"""Build Daml docs lifecycle reports from versioned docs JSON snapshots."""

from __future__ import annotations

import copy
import re
from typing import Any

from x2mdx.daml_json.models import DamlDocsReport, DamlDocsSources

SNAPSHOT_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-snapshot\.(\d{8})\.(\d+)$")
RC_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-rc(\d+)$")
STABLE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def version_sort_key(version: str) -> tuple[Any, ...]:
    if m := SNAPSHOT_VERSION_RE.fullmatch(version):
        major, minor, patch, yyyymmdd, seq = m.groups()
        return (0, int(major), int(minor), int(patch), 0, int(yyyymmdd), int(seq))
    if m := RC_VERSION_RE.fullmatch(version):
        major, minor, patch, rc = m.groups()
        return (0, int(major), int(minor), int(patch), 1, int(rc), 0)
    if m := STABLE_VERSION_RE.fullmatch(version):
        major, minor, patch = m.groups()
        return (0, int(major), int(minor), int(patch), 2, 0, 0)
    return (1, version)


def _module_name(module_doc: dict[str, Any]) -> str:
    return str(module_doc.get("md_name", "")).strip()


def extract_tagged_warning_messages(warns: Any, tag: str) -> list[str]:
    values: list[Any]
    if warns is None:
        values = []
    elif isinstance(warns, list):
        values = warns
    else:
        values = [warns]

    out: list[str] = []

    def append_texts(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                append_texts(item)
            return
        if node is None:
            return
        text = str(node).strip()
        if text:
            out.append(text)

    for entry in values:
        if not isinstance(entry, dict):
            continue
        if tag in entry:
            append_texts(entry[tag])

    deduped: list[str] = []
    seen: set[str] = set()
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _compute_deprecation_first_seen(version_modules: list[tuple[str, list[dict[str, Any]]]]) -> dict[str, str]:
    first_seen: dict[str, str] = {}
    for version, modules in version_modules:
        for module in modules:
            module_name = _module_name(module)
            if not module_name or module_name in first_seen:
                continue
            if extract_tagged_warning_messages(module.get("md_warn"), "DeprecatedData"):
                first_seen[module_name] = version
    return first_seen


def _build_publish_modules(
    version_modules: list[tuple[str, list[dict[str, Any]]]],
    *,
    publish_version: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str | None]]]:
    ordered_versions = [version for version, _modules in version_modules]
    if publish_version not in ordered_versions:
        raise ValueError(
            f"Publish version '{publish_version}' is not present in selected snapshots: {ordered_versions}"
        )

    publish_index = ordered_versions.index(publish_version)
    scoped_versions = version_modules[: publish_index + 1]

    module_history: dict[str, dict[str, Any]] = {}
    modules_by_version: dict[str, list[dict[str, Any]]] = {}
    for version, modules in scoped_versions:
        modules_by_version[version] = modules
        for module_doc in modules:
            name = _module_name(module_doc)
            if not name:
                continue
            history = module_history.setdefault(name, {"versions": [], "docs": {}})
            history["versions"].append(version)
            history["docs"][version] = module_doc

    publish_modules = modules_by_version[publish_version]
    merged_modules: list[dict[str, Any]] = []
    publish_names: set[str] = set()
    for module_doc in publish_modules:
        name = _module_name(module_doc)
        if not name:
            continue
        merged_modules.append(copy.deepcopy(module_doc))
        publish_names.add(name)

    lifecycle: dict[str, dict[str, str | None]] = {}
    for name, history in module_history.items():
        present_versions = list(history["versions"])
        introduced_in = present_versions[0]
        last_seen_in = present_versions[-1]
        removed_in: str | None = None
        status = "active" if publish_version in present_versions else "unknown"

        if status != "active":
            last_seen_index = ordered_versions.index(last_seen_in)
            for candidate in ordered_versions[last_seen_index + 1 : publish_index + 1]:
                if candidate not in present_versions:
                    removed_in = candidate
                    break
            if removed_in is not None:
                status = "removed"

        lifecycle[name] = {
            "introduced_in": introduced_in,
            "last_seen_in": last_seen_in,
            "removed_in": removed_in,
            "status": status,
        }

        if status == "removed" and name not in publish_names:
            merged_modules.append(copy.deepcopy(history["docs"][last_seen_in]))
            publish_names.add(name)

    return merged_modules, lifecycle


def build_daml_doc_report_from_sources(
    sources: DamlDocsSources,
    *,
    source_name: str,
    version_filter: str,
    publish_version: str | None = None,
) -> DamlDocsReport:
    ordered_snapshots = sorted(sources.snapshots, key=lambda snapshot: version_sort_key(snapshot.version))
    version_modules = [(snapshot.version, snapshot.modules) for snapshot in ordered_snapshots]
    selected_publish_version = publish_version or sources.publish_version or ordered_snapshots[-1].version
    merged_modules, lifecycle = _build_publish_modules(
        version_modules,
        publish_version=selected_publish_version,
    )
    deprecation_first_seen = _compute_deprecation_first_seen(version_modules)
    return DamlDocsReport(
        source_name=source_name,
        version_filter=version_filter,
        publish_version=selected_publish_version,
        versions=[snapshot.version for snapshot in ordered_snapshots],
        modules=merged_modules,
        module_lifecycle=lifecycle,
        module_deprecation_first_seen=deprecation_first_seen,
    )

