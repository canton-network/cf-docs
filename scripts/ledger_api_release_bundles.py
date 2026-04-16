#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import shutil
import tarfile
import urllib.request
from pathlib import Path
from typing import Any


USER_AGENT = "digital-asset-docs-x2mdx/1.0"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def selected_versions(source_config: dict[str, Any], include_versions: set[str] | None) -> list[dict[str, str]]:
    configured_versions = source_config.get("versions")
    if not isinstance(configured_versions, list) or not all(isinstance(item, dict) for item in configured_versions):
        raise ValueError("Source config must define a `versions` list of objects")

    selected: list[dict[str, str]] = []
    for entry in configured_versions:
        version = str(entry.get("version") or "")
        canton_version = str(entry.get("canton_version") or "")
        if not version or not canton_version:
            raise ValueError("Each source version entry must define `version` and `canton_version`")
        if include_versions is not None and version not in include_versions:
            continue
        selected.append({"version": version, "canton_version": canton_version})

    if not selected:
        raise ValueError("No Ledger API versions selected")

    selected.sort(key=lambda entry: version_key(entry["version"]))
    return selected


def bundle_url(source_config: dict[str, Any], version_entry: dict[str, str]) -> str:
    template = source_config.get("release_url_template")
    if not isinstance(template, str) or not template:
        raise ValueError("Source config must define `release_url_template`")
    return template.format(canton_version=version_entry["canton_version"])


def manifest_source_path(source_config: dict[str, Any], spec_filename: str) -> str:
    prefix = source_config.get("source_path_prefix")
    if not isinstance(prefix, str) or not prefix:
        raise ValueError("Source config must define `source_path_prefix`")
    return f"{prefix.rstrip('/')}/{spec_filename}"


def bundle_archive_name(version_entry: dict[str, str]) -> str:
    return f"canton-open-source-{version_entry['canton_version']}.tar.gz"


def bundle_archive_path(cache_dir: Path, version_entry: dict[str, str]) -> Path:
    return cache_dir / version_entry["version"] / bundle_archive_name(version_entry)


def ensure_bundle_archive(
    *,
    source_config: dict[str, Any],
    cache_dir: Path,
    version_entry: dict[str, str],
    force_refresh: bool,
) -> Path:
    output_path = bundle_archive_path(cache_dir, version_entry)
    if output_path.exists() and not force_refresh:
        return output_path

    url = bundle_url(source_config, version_entry)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.name}.{os.getpid()}.tmp")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response, temp_path.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    temp_path.replace(output_path)
    return output_path


def read_bundle_spec_text(archive_path: Path, *, source_config: dict[str, Any], spec_filename: str) -> str:
    bundle_spec_dir = source_config.get("bundle_spec_dir")
    if not isinstance(bundle_spec_dir, str) or not bundle_spec_dir:
        raise ValueError("Source config must define `bundle_spec_dir`")

    wanted_suffix = f"{bundle_spec_dir.rstrip('/')}/{spec_filename}"
    with tarfile.open(archive_path, "r:gz") as handle:
        member = next(
            (
                item
                for item in handle.getmembers()
                if item.isfile() and item.name.endswith(wanted_suffix)
            ),
            None,
        )
        if member is None:
            raise FileNotFoundError(f"Spec '{wanted_suffix}' not found in bundle {archive_path}")
        extracted = handle.extractfile(member)
        if extracted is None:
            raise FileNotFoundError(f"Failed to read '{member.name}' from bundle {archive_path}")
        return extracted.read().decode("utf-8")


def materialize_bundle_spec(
    *,
    source_config: dict[str, Any],
    cache_dir: Path,
    version_entry: dict[str, str],
    spec_filename: str,
    output_path: Path,
    force_refresh: bool,
) -> Path:
    archive_path = ensure_bundle_archive(
        source_config=source_config,
        cache_dir=cache_dir,
        version_entry=version_entry,
        force_refresh=force_refresh,
    )
    spec_text = read_bundle_spec_text(archive_path, source_config=source_config, spec_filename=spec_filename)
    if output_path.exists():
        existing_text = output_path.read_text(encoding="utf-8")
        existing_lines = [line for line in existing_text.splitlines() if line]
        if existing_lines:
            indent_candidates = [re.match(r"^\s*", line).group(0) for line in existing_lines]
            non_empty_indents = [indent for indent in indent_candidates if indent]
            shared_prefix = min(non_empty_indents, key=len) if non_empty_indents else ""
            if shared_prefix:
                spec_lines = spec_text.splitlines()
                spec_text = "\n".join(
                    f"{shared_prefix}{line}" if line else line
                    for line in spec_lines
                )
                if spec_text and not spec_text.endswith("\n"):
                    spec_text += "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not force_refresh and output_path.read_text(encoding="utf-8") == spec_text:
        return output_path
    output_path.write_text(spec_text, encoding="utf-8")
    return output_path
