#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import generate_canton_protobuf_history as canton_protobuf_history


USER_AGENT = "digital-asset-docs-x2mdx/1.0"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def github_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def selected_releases(
    *,
    source_config: dict[str, Any],
    include_versions: set[str] | None,
) -> list[dict[str, str]]:
    release_repo = source_config.get("release_repo")
    if not isinstance(release_repo, str) or not release_repo:
        raise ValueError("Source config must define release_repo")
    tag_regex = source_config.get("tag_regex")
    if not isinstance(tag_regex, str) or not tag_regex:
        raise ValueError("Source config must define tag_regex")
    asset_template = source_config.get("asset_template")
    if not isinstance(asset_template, str) or not asset_template:
        raise ValueError("Source config must define asset_template")
    min_version = source_config.get("min_version") or "0.0.0"
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
        raise ValueError(f"No published releases matched the configured Splice OpenAPI bundle selection for {release_repo}")
    return releases


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


def materialize_release_fixtures(
    *,
    cache_dir: Path,
    release: dict[str, str],
    force_refresh: bool,
) -> list[str]:
    fixture_dir = cache_dir / "fixtures" / release["version"]
    if fixture_dir.exists() and force_refresh:
        shutil.rmtree(fixture_dir)
    if fixture_dir.exists():
        existing = sorted(
            path.name
            for path in fixture_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
        )
        if existing:
            return existing

    archive = ensure_archive(cache_dir=cache_dir, release=release, force_refresh=force_refresh)
    fixture_dir.mkdir(parents=True, exist_ok=True)

    filenames: list[str] = []
    seen: set[str] = set()
    with tarfile.open(archive, "r:gz") as handle:
        for member in handle.getmembers():
            if not member.isfile():
                continue
            filename = Path(member.name).name
            if Path(filename).suffix.lower() not in {".yaml", ".yml"}:
                continue
            if filename in seen:
                raise ValueError(f"Duplicate YAML filename '{filename}' found in {archive}")
            extracted = handle.extractfile(member)
            if extracted is None:
                raise FileNotFoundError(f"Failed to extract '{member.name}' from {archive}")
            (fixture_dir / filename).write_bytes(extracted.read())
            seen.add(filename)
            filenames.append(filename)

    filenames.sort()
    if not filenames:
        raise FileNotFoundError(f"No YAML files found in {archive}")
    return filenames


def write_manifest(
    *,
    source_config: dict[str, Any],
    cache_dir: Path,
    manifest_path: Path,
    releases: list[dict[str, str]],
    source_name: str,
) -> Path:
    source_path_prefix = source_config.get("source_path_prefix") or "openapi"
    if not isinstance(source_path_prefix, str):
        raise ValueError("source_path_prefix must be a string")
    entries: list[dict[str, str]] = []
    for release in releases:
        for filename in release["fixture_filenames"]:
            entries.append(
                {
                    "version": release["version"],
                    "url": release["download_url"],
                    "source_path": f"{source_path_prefix.rstrip('/')}/{filename}",
                    "fixture_path": str((cache_dir / "fixtures" / release["version"] / filename).resolve()),
                }
            )

    manifest = {
        "source": source_name,
        "versions": entries,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    return manifest_path


def slugify(value: str) -> str:
    output = value.lower()
    output = re.sub(r"[^a-z0-9]+", "-", output)
    output = re.sub(r"-{2,}", "-", output).strip("-")
    return output


def normalized_spec_pages(source_config: dict[str, Any]) -> list[dict[str, str]]:
    spec_pages = source_config.get("spec_pages")
    if spec_pages is None:
        legacy_filenames = source_config.get("spec_filenames")
        if not isinstance(legacy_filenames, list) or not all(
            isinstance(item, str) and item for item in legacy_filenames
        ):
            raise ValueError("Source config must define spec_pages or spec_filenames")
        return [
            {
                "filename": spec_filename,
                "output_filename": f"{slugify(spec_filename)}.mdx",
            }
            for spec_filename in legacy_filenames
        ]

    if not isinstance(spec_pages, list) or not spec_pages:
        raise ValueError("spec_pages must be a non-empty list")

    normalized: list[dict[str, str]] = []
    for entry in spec_pages:
        if not isinstance(entry, dict):
            raise ValueError("Each spec_pages entry must be an object")
        filename = entry.get("filename")
        if not isinstance(filename, str) or not filename:
            raise ValueError("Each spec_pages entry must define a non-empty filename")
        output_filename = entry.get("output_filename")
        if output_filename is None:
            output_filename = f"{slugify(filename)}.mdx"
        if not isinstance(output_filename, str) or not output_filename.endswith(".mdx"):
            raise ValueError("Each spec_pages entry must define an output_filename ending in .mdx")
        normalized.append(
            {
                "filename": filename,
                "output_filename": output_filename,
            }
        )
    return normalized


def page_output_path(output_dir: Path, spec_page: dict[str, str]) -> Path:
    return output_dir / spec_page["output_filename"]


def page_ref(output_dir: Path, docs_json_path: Path, spec_page: dict[str, str]) -> str:
    return canton_protobuf_history.docs_json_page_ref(page_output_path(output_dir, spec_page), docs_json_path)


def build_nav_group(
    *,
    docs_json_path: Path,
    output_dir: Path,
    nav_group_label: str,
    spec_pages: list[dict[str, str]],
) -> tuple[dict[str, Any], set[str]]:
    refs = [page_ref(output_dir, docs_json_path, spec_page) for spec_page in spec_pages]
    return {"group": nav_group_label, "pages": refs}, set(refs)


def legacy_nav_refs(
    *,
    docs_json_path: Path,
    output_dir: Path,
    spec_pages: list[dict[str, str]],
) -> set[str]:
    refs = {
        canton_protobuf_history.docs_json_page_ref(output_dir / "index.mdx", docs_json_path),
    }
    for spec_page in spec_pages:
        refs.add(
            canton_protobuf_history.docs_json_page_ref(
                output_dir / "specs" / f"{slugify(spec_page['filename'])}.mdx",
                docs_json_path,
            )
        )
    return refs


def insert_group(items: list[Any], *, group: dict[str, Any], after_group: str | None) -> None:
    if after_group:
        for index, item in enumerate(items):
            if isinstance(item, dict) and item.get("group") == after_group:
                items.insert(index + 1, group)
                return
    items.append(group)


def ensure_group_path(
    items: list[Any],
    group_path: list[str],
    *,
    top_level_insert_after_group: str | None,
) -> list[Any]:
    current_pages = items
    top_level_items = items
    for depth, label in enumerate(group_path):
        group = next(
            (item for item in current_pages if isinstance(item, dict) and item.get("group") == label),
            None,
        )
        if group is None:
            group = {"group": label, "pages": []}
            if depth == 0:
                insert_group(top_level_items, group=group, after_group=top_level_insert_after_group)
            else:
                current_pages.append(group)
        pages = group.get("pages")
        if not isinstance(pages, list):
            pages = []
            group["pages"] = pages
        current_pages = pages
    return current_pages


def update_docs_navigation(
    *,
    docs_json_path: Path,
    dropdown_label: str,
    parent_groups: list[str],
    top_level_insert_after_group: str | None,
    output_dir: Path,
    nav_group_label: str,
    spec_pages: list[dict[str, str]],
) -> None:
    docs = load_json(docs_json_path)
    navigation = docs.get("navigation")
    if not isinstance(navigation, dict):
        raise ValueError(f"docs.json navigation must be an object: {docs_json_path}")
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

    nav_group, generated_refs = build_nav_group(
        docs_json_path=docs_json_path,
        output_dir=output_dir,
        nav_group_label=nav_group_label,
        spec_pages=spec_pages,
    )
    generated_refs |= legacy_nav_refs(
        docs_json_path=docs_json_path,
        output_dir=output_dir,
        spec_pages=spec_pages,
    )
    dropdown["pages"] = canton_protobuf_history.prune_nav_items(
        pages,
        page_refs=generated_refs,
        group_labels={nav_group_label},
    )
    target_pages = ensure_group_path(
        dropdown["pages"],
        parent_groups,
        top_level_insert_after_group=top_level_insert_after_group,
    )
    insert_group(target_pages, group=nav_group, after_group=None)
    docs_json_path.write_text(json.dumps(docs, indent=2) + "\n", encoding="utf-8")
    print(f"Updated docs navigation: {docs_json_path}")


def build_command(
    *,
    source_config: dict[str, Any],
    manifest_path: Path,
    output_file: Path,
    spec_page: dict[str, str],
    versions: list[str],
    source_name: str,
    version_filter: str,
) -> list[str]:
    source_path_prefix = source_config.get("source_path_prefix") or "openapi"
    if not isinstance(source_path_prefix, str) or not source_path_prefix:
        raise ValueError("source_path_prefix must be a non-empty string")
    spec_filename = spec_page["filename"]

    command = [
        "x2mdx",
        "openapi",
        "build-api-pages-from-manifest",
        "--manifest",
        str(manifest_path),
        "--root",
        source_path_prefix,
        "--output-file",
        str(output_file),
        "--source-name",
        source_name,
        "--version-filter",
        version_filter,
    ]
    command.extend(["--include-spec-pattern", rf"^{re.escape(spec_filename)}$"])
    for mapping in source_config.get("canonical_paths", []):
        command.extend(["--canonical-path", mapping])
    for prefix in source_config.get("priority_prefixes", []):
        command.extend(["--priority-prefix", prefix])
    for version in versions:
        command.extend(["--version", version])
    return command


def render_reference(
    *,
    source_config_path: Path,
    cache_dir: Path,
    manifest_path: Path,
    output_dir: Path,
    docs_json_path: Path,
    dropdown_label: str,
    include_versions: set[str] | None,
    min_version_override: str | None,
    source_name: str,
    version_filter: str,
    force_refresh: bool,
) -> None:
    source_config = load_json(source_config_path)
    spec_pages = normalized_spec_pages(source_config)
    nav_parent_groups = source_config.get("nav_parent_groups")
    if not isinstance(nav_parent_groups, list) or not all(isinstance(item, str) and item for item in nav_parent_groups):
        raise ValueError("nav_parent_groups must be a list of non-empty strings")
    nav_group_label = source_config.get("nav_group_label")
    if not isinstance(nav_group_label, str) or not nav_group_label:
        raise ValueError("nav_group_label must be a non-empty string")
    top_level_insert_after_group = source_config.get("top_level_insert_after_group")
    if top_level_insert_after_group is not None and not isinstance(top_level_insert_after_group, str):
        raise ValueError("top_level_insert_after_group must be a string if present")

    if min_version_override:
        source_config = dict(source_config)
        source_config["min_version"] = min_version_override

    releases = selected_releases(source_config=source_config, include_versions=include_versions)
    for release in releases:
        release["fixture_filenames"] = materialize_release_fixtures(
            cache_dir=cache_dir,
            release=release,
            force_refresh=force_refresh,
        )

    write_manifest(
        source_config=source_config,
        cache_dir=cache_dir,
        manifest_path=manifest_path,
        releases=releases,
        source_name=source_name,
    )

    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    versions = [release["version"] for release in releases]
    for spec_page in spec_pages:
        output_file = page_output_path(output_dir, spec_page)
        command = build_command(
            source_config=source_config,
            manifest_path=manifest_path,
            output_file=output_file,
            spec_page=spec_page,
            versions=versions,
            source_name=source_name,
            version_filter=version_filter,
        )
        print("Running:", " ".join(command))
        subprocess.run(command, check=True)
        if not output_file.exists():
            raise FileNotFoundError(f"Expected generated spec page not found: {output_file}")

    update_docs_navigation(
        docs_json_path=docs_json_path,
        dropdown_label=dropdown_label,
        parent_groups=nav_parent_groups,
        top_level_insert_after_group=top_level_insert_after_group,
        output_dir=output_dir,
        nav_group_label=nav_group_label,
        spec_pages=spec_pages,
    )
