#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from validate_splice_mintlify_openapi_nav import validate_splice_nav

REPO_ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "digital-asset-docs-mintlify-openapi/1.0"
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "mintlify-openapi" / "splice-openapi" / "source-artifacts.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "mintlify-openapi" / "splice-openapi"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def github_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def selected_releases(
    *,
    source_config: dict[str, Any],
    include_versions: set[str] | None,
) -> list[dict[str, str]]:
    release_repo = source_config.get("release_repo")
    tag_regex = source_config.get("tag_regex")
    asset_template = source_config.get("asset_template")
    min_version = source_config.get("min_version") or "0.0.0"
    if not isinstance(release_repo, str) or not release_repo:
        raise ValueError("Source config must define release_repo")
    if not isinstance(tag_regex, str) or not tag_regex:
        raise ValueError("Source config must define tag_regex")
    if not isinstance(asset_template, str) or not asset_template:
        raise ValueError("Source config must define asset_template")
    if not isinstance(min_version, str):
        raise ValueError("min_version must be a string")

    matcher = re.compile(tag_regex)
    minimum_key = version_key(min_version)
    releases: list[dict[str, str]] = []
    page = 1
    while True:
        payload = github_json(
            f"https://api.github.com/repos/{release_repo}/releases?per_page=100&page={page}"
        )
        if not isinstance(payload, list):
            raise ValueError(f"Expected list payload from GitHub releases API for {release_repo}")
        if not payload:
            break
        for release in payload:
            if not isinstance(release, dict):
                continue
            if release.get("draft") or release.get("prerelease"):
                continue
            tag_name = release.get("tag_name")
            if not isinstance(tag_name, str):
                continue
            match = matcher.fullmatch(tag_name)
            if not match:
                continue
            version = match.groupdict().get("version") or tag_name.removeprefix("v")
            if version_key(version) < minimum_key:
                continue
            if include_versions is not None and version not in include_versions:
                continue
            asset_name = asset_template.format(version=version)
            assets = release.get("assets")
            if not isinstance(assets, list):
                continue
            asset = next(
                (
                    item
                    for item in assets
                    if isinstance(item, dict) and item.get("name") == asset_name
                ),
                None,
            )
            if asset is None:
                continue
            download_url = asset.get("browser_download_url")
            if not isinstance(download_url, str) or not download_url:
                continue
            releases.append(
                {
                    "version": version,
                    "tag": tag_name,
                    "asset_name": asset_name,
                    "download_url": download_url,
                }
            )
        if len(payload) < 100:
            break
        page += 1

    releases.sort(key=lambda entry: version_key(entry["version"]))
    if not releases:
        raise ValueError(f"No published releases matched the configured Splice OpenAPI selection for {release_repo}")
    return releases


def configured_versions(source_config: dict[str, Any]) -> set[str] | None:
    configured = source_config.get("versions")
    if configured is None:
        return None
    if not isinstance(configured, list) or not all(isinstance(item, str) and item for item in configured):
        raise ValueError("Source config versions must be a list of non-empty strings")
    return set(configured)


def resolve_publish_release(
    *,
    source_config: dict[str, Any],
    releases: list[dict[str, str]],
    requested_version: str | None,
) -> dict[str, str]:
    publish_version = requested_version
    if publish_version is None:
        configured = source_config.get("publish_version")
        if isinstance(configured, str) and configured.strip():
            publish_version = configured.strip()

    if publish_version is None:
        return releases[-1]

    selected = next((entry for entry in releases if entry["version"] == publish_version), None)
    if selected is None:
        available = ", ".join(entry["version"] for entry in releases)
        raise ValueError(f"Publish version '{publish_version}' not found in selected releases: {available}")
    return selected


def archive_path(cache_dir: Path, *, release: dict[str, str]) -> Path:
    return cache_dir / "archives" / release["version"] / release["asset_name"]


def ensure_archive(
    *,
    cache_dir: Path,
    release: dict[str, str],
    force_refresh: bool,
) -> Path:
    output_path = archive_path(cache_dir, release=release)
    if output_path.exists() and not force_refresh:
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.name}.{os.getpid()}.tmp")
    request = urllib.request.Request(
        release["download_url"],
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=180) as response, temp_path.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    temp_path.replace(output_path)
    return output_path


def normalized_families(source_config: dict[str, Any]) -> list[dict[str, Any]]:
    families = source_config.get("families")
    if not isinstance(families, list) or not families:
        raise ValueError("Source config must define a non-empty families list")

    normalized: list[dict[str, Any]] = []
    for family in families:
        if not isinstance(family, dict):
            raise ValueError("Each family entry must be an object")
        group = family.get("group")
        specs = family.get("specs")
        if not isinstance(group, str) or not group:
            raise ValueError("Each family must define a non-empty group")
        if not isinstance(specs, list) or not specs:
            raise ValueError(f"Family '{group}' must define a non-empty specs list")
        normalized_specs: list[dict[str, Any]] = []
        for spec in specs:
            if not isinstance(spec, dict):
                raise ValueError(f"Spec entries for family '{group}' must be objects")
            filename = spec.get("filename")
            nav_label = spec.get("nav_label")
            source_ref = spec.get("source")
            directory = spec.get("directory")
            if not all(isinstance(item, str) and item for item in (filename, nav_label, source_ref, directory)):
                raise ValueError(
                    f"Specs for family '{group}' must define non-empty filename, nav_label, source, and directory"
                )
            normalized_specs.append(
                {
                    "filename": filename,
                    "nav_label": nav_label,
                    "source": source_ref,
                    "directory": directory,
                }
            )
        normalized.append({"group": group, "specs": normalized_specs})
    return normalized


def extract_spec_bytes(
    *,
    archive: Path,
    spec_filenames: set[str],
) -> dict[str, bytes]:
    extracted: dict[str, bytes] = {}
    with tarfile.open(archive, "r:gz") as handle:
        for member in handle.getmembers():
            if not member.isfile():
                continue
            filename = Path(member.name).name
            if filename not in spec_filenames:
                continue
            raw_handle = handle.extractfile(member)
            if raw_handle is None:
                raise FileNotFoundError(f"Failed to extract '{member.name}' from {archive}")
            extracted[filename] = raw_handle.read()

    missing = sorted(spec_filenames - extracted.keys())
    if missing:
        joined = ", ".join(missing)
        raise FileNotFoundError(f"Archive {archive} did not contain expected OpenAPI specs: {joined}")
    return extracted


def render_output_bytes(*, spec_bytes: bytes, output_path: Path) -> bytes:
    if output_path.suffix not in {".yaml", ".yml"}:
        return spec_bytes

    text = spec_bytes.decode("utf-8")
    filtered_lines = [
        line
        for line in text.splitlines()
        if not re.fullmatch(r"\s*required:\s*\[\s*\]\s*", line)
    ]
    normalized_text = "\n".join(filtered_lines).rstrip() + "\n"
    normalized_text = add_missing_operation_summaries(normalized_text)
    return normalized_text.encode("utf-8")


def missing_operation_summaries(spec: dict[str, Any]) -> set[tuple[str, str]]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return set()

    missing: set[tuple[str, str]] = set()
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            summary = operation.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                missing.add((path, method.lower()))
    return missing


def add_missing_operation_summaries(text: str) -> str:
    spec = yaml.safe_load(text)
    if not isinstance(spec, dict):
        raise ValueError("Expected generated OpenAPI YAML to parse as an object")

    missing = missing_operation_summaries(spec)
    if not missing:
        return text

    lines = text.splitlines()
    output_lines: list[str] = []
    in_paths = False
    current_path: str | None = None

    for line in lines:
        output_lines.append(line)

        if re.fullmatch(r"paths:\s*", line):
            in_paths = True
            current_path = None
            continue

        if not in_paths:
            continue

        if line and not line.startswith(" "):
            in_paths = False
            current_path = None
            continue

        path_match = re.fullmatch(r"  (?P<path>/.*):\s*", line)
        if path_match:
            current_path = path_match.group("path")
            continue

        method_match = re.fullmatch(r"    (?P<method>get|put|post|delete|options|head|patch|trace):\s*", line)
        if current_path is None or method_match is None:
            continue

        method = method_match.group("method")
        if (current_path, method) in missing:
            output_lines.append(f'      summary: "{current_path}"')

    rendered = "\n".join(output_lines).rstrip() + "\n"
    parsed = yaml.safe_load(rendered)
    if not isinstance(parsed, dict):
        raise ValueError("Generated OpenAPI YAML stopped parsing after summary insertion")
    remaining = missing_operation_summaries(parsed)
    if remaining:
        details = ", ".join(f"{method.upper()} {path}" for path, method in sorted(remaining))
        raise ValueError(f"Failed to insert generated summaries for OpenAPI operations: {details}")
    return rendered


def write_managed_specs(
    *,
    docs_root: Path,
    source_config: dict[str, Any],
    families: list[dict[str, Any]],
    spec_bytes: dict[str, bytes],
) -> list[Path]:
    managed_root = source_config.get("managed_openapi_root")
    if not isinstance(managed_root, str) or not managed_root:
        raise ValueError("Source config must define managed_openapi_root")

    output_root = docs_root / managed_root
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []
    for family in families:
        for spec in family["specs"]:
            output_path = docs_root / spec["source"]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(
                render_output_bytes(
                    spec_bytes=spec_bytes[spec["filename"]],
                    output_path=output_path,
                )
            )
            written_paths.append(output_path)
            print(f"Published Mintlify OpenAPI source: {output_path}")
    return written_paths


def cleanup_legacy_outputs(*, docs_root: Path, source_config: dict[str, Any]) -> None:
    legacy_paths = source_config.get("legacy_cleanup_paths")
    if not isinstance(legacy_paths, list):
        return
    for relative_path in legacy_paths:
        if not isinstance(relative_path, str) or not relative_path:
            continue
        absolute_path = docs_root / relative_path
        if absolute_path.is_dir():
            shutil.rmtree(absolute_path, ignore_errors=True)
        elif absolute_path.exists():
            absolute_path.unlink()


def enabled_nav_specs(source_config: dict[str, Any]) -> set[str] | None:
    enabled = source_config.get("enabled_nav_specs")
    if enabled is None:
        return None
    if not isinstance(enabled, list):
        raise ValueError("enabled_nav_specs must be a list when set")

    normalized: set[str] = set()
    for item in enabled:
        if not isinstance(item, str) or not item:
            raise ValueError("enabled_nav_specs entries must be non-empty strings")
        normalized.add(item)
    return normalized


def filtered_families_for_navigation(
    *,
    families: list[dict[str, Any]],
    enabled_specs: set[str] | None,
) -> list[dict[str, Any]]:
    if enabled_specs is None:
        return families

    filtered: list[dict[str, Any]] = []
    for family in families:
        specs = [spec for spec in family["specs"] if spec["filename"] in enabled_specs]
        if specs:
            filtered.append({"group": family["group"], "specs": specs})
    return filtered


def openapi_operation_page_refs(spec: dict[str, Any]) -> list[str]:
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


def build_splice_openapi_nav_entry(*, docs_root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    openapi_path = docs_root / spec["source"]
    payload = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected OpenAPI spec to parse as an object: {openapi_path}")
    entry: dict[str, Any] = {
        "group": spec["nav_label"],
        "openapi": {
            "source": spec["source"],
            "directory": spec["directory"],
        },
        "pages": openapi_operation_page_refs(payload),
    }
    return entry


def build_splice_group_pages(*, docs_root: Path, families: list[dict[str, Any]]) -> list[Any]:
    pages: list[Any] = []
    for family in families:
        family_pages: list[dict[str, Any]] = []
        for spec in family["specs"]:
            family_pages.append(build_splice_openapi_nav_entry(docs_root=docs_root, spec=spec))
        pages.append({"group": family["group"], "pages": family_pages})
    return pages


def update_docs_navigation(
    *,
    docs_json_path: Path,
    source_config: dict[str, Any],
    families: list[dict[str, Any]],
) -> None:
    payload = load_json(docs_json_path)
    navigation = payload.get("navigation")
    if not isinstance(navigation, dict):
        raise ValueError(f"docs.json missing navigation object: {docs_json_path}")
    dropdowns = navigation.get("dropdowns")
    if not isinstance(dropdowns, list):
        raise ValueError(f"docs.json navigation.dropdowns must be a list: {docs_json_path}")

    dropdown_label = source_config.get("nav_dropdown") or "API Reference"
    if not isinstance(dropdown_label, str):
        raise ValueError("nav_dropdown must be a string")
    top_level_group_label = source_config.get("top_level_group_label") or "Splice APIs"
    if not isinstance(top_level_group_label, str):
        raise ValueError("top_level_group_label must be a string")
    insert_after_group = source_config.get("insert_after_group")
    if insert_after_group is not None and not isinstance(insert_after_group, str):
        raise ValueError("insert_after_group must be a string when set")
    enabled_specs = enabled_nav_specs(source_config)
    navigation_families = filtered_families_for_navigation(families=families, enabled_specs=enabled_specs)

    dropdown = next(
        (item for item in dropdowns if isinstance(item, dict) and item.get("dropdown") == dropdown_label),
        None,
    )
    if dropdown is None:
        raise ValueError(f"Dropdown not found in docs.json: {dropdown_label}")
    pages = dropdown.get("pages")
    if not isinstance(pages, list):
        raise ValueError(f"Dropdown does not expose a pages list: {dropdown_label}")

    deduped_pages: list[Any] = []
    for item in pages:
        if isinstance(item, dict) and item.get("group") == top_level_group_label:
            continue
        deduped_pages.append(item)

    if not navigation_families:
        return

    insert_at = len(deduped_pages)
    if insert_after_group is not None:
        for index, item in enumerate(deduped_pages):
            if isinstance(item, dict) and item.get("group") == insert_after_group:
                insert_at = index + 1
                break

    deduped_pages.insert(
        insert_at,
        {
            "group": top_level_group_label,
            "pages": build_splice_group_pages(docs_root=docs_json_path.parent, families=navigation_families),
        },
    )
    dropdown["pages"] = deduped_pages
    docs_json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish the latest configured Splice OpenAPI specs into docs-main/openapi so Mintlify can "
            "render them natively, and wire any enabled spec groups into docs.json."
        )
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument(
        "--publish-version",
        help="Explicit decentralized-canton-sync release version whose OpenAPI bundle should drive the Mintlify view.",
    )
    parser.add_argument(
        "--version",
        action="append",
        help="Restrict candidate versions before selecting the publish version. Repeat to filter the set.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Refresh cached decentralized-canton-sync release bundles before publishing specs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    include_versions = set(args.version) if args.version else configured_versions(source_config)
    releases = selected_releases(source_config=source_config, include_versions=include_versions)
    publish_release = resolve_publish_release(
        source_config=source_config,
        releases=releases,
        requested_version=args.publish_version,
    )
    archive = ensure_archive(
        cache_dir=Path(args.cache_dir).resolve(),
        release=publish_release,
        force_refresh=args.force_refresh,
    )
    families = normalized_families(source_config)
    spec_filenames = {spec["filename"] for family in families for spec in family["specs"]}
    spec_bytes = extract_spec_bytes(archive=archive, spec_filenames=spec_filenames)

    docs_json_path = Path(args.docs_json).resolve()
    docs_root = docs_json_path.parent
    write_managed_specs(
        docs_root=docs_root,
        source_config=source_config,
        families=families,
        spec_bytes=spec_bytes,
    )
    cleanup_legacy_outputs(docs_root=docs_root, source_config=source_config)
    update_docs_navigation(
        docs_json_path=docs_json_path,
        source_config=source_config,
        families=families,
    )
    validate_splice_nav(
        source_config_path=Path(args.source_config).resolve(),
        docs_json_path=docs_json_path,
    )
    print(f"Updated docs navigation: {docs_json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
