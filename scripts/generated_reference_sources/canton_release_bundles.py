from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import generate_canton_protobuf_history as canton_protobuf_history

from generated_reference_sources.common import SourceUpdate, load_json, write_json


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_LABEL = "JSON Ledger API release bundle"
DEFAULT_CANTON_REMOTE = "https://github.com/digital-asset/canton.git"
DEFAULT_TIMEOUT_SECONDS = 20.0
USER_AGENT = "cf-docs-generated-reference-source-updater"
DEFAULT_CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "x2mdx"
DEFAULT_REPO_DIR = DEFAULT_CACHE_ROOT / "protobuf-history" / "repos" / "canton"


@dataclass(frozen=True)
class LedgerApiVersionConfig:
    raw: dict[str, object]
    version: str
    canton_version: str


@dataclass(frozen=True)
class LedgerApiSourceConfig:
    raw: dict[str, object]
    publish_version: str
    release_url_template: str
    versions: tuple[LedgerApiVersionConfig, ...]


def parse_source_config(path: Path) -> LedgerApiSourceConfig:
    raw_json = load_json(path)
    publish_version = raw_json.get("publish_version")
    release_url_template = raw_json.get("release_url_template")
    versions_json = raw_json.get("versions")
    if not isinstance(publish_version, str) or not publish_version:
        raise ValueError(f"{path} must define non-empty publish_version")
    if not isinstance(release_url_template, str) or not release_url_template:
        raise ValueError(f"{path} must define non-empty release_url_template")
    if not isinstance(versions_json, list) or not versions_json:
        raise ValueError(f"{path} must define a non-empty versions list")

    versions: list[LedgerApiVersionConfig] = []
    for index, entry_json in enumerate(versions_json):
        if not isinstance(entry_json, dict):
            raise ValueError(f"{path} versions[{index}] must be an object")
        version = entry_json.get("version")
        canton_version = entry_json.get("canton_version")
        if not isinstance(version, str) or not version:
            raise ValueError(f"{path} versions[{index}] must define version")
        if not isinstance(canton_version, str) or not canton_version:
            raise ValueError(f"{path} versions[{version}] must define canton_version")
        versions.append(
            LedgerApiVersionConfig(
                raw=dict(entry_json),
                version=version,
                canton_version=canton_version,
            )
        )
    return LedgerApiSourceConfig(
        raw=raw_json,
        publish_version=publish_version,
        release_url_template=release_url_template,
        versions=tuple(versions),
    )


def release_url(source_config: LedgerApiSourceConfig, *, canton_version: str) -> str:
    return source_config.release_url_template.format(canton_version=canton_version)


def release_bundle_exists(
    source_config: LedgerApiSourceConfig,
    *,
    canton_version: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    request = urllib.request.Request(
        release_url(source_config, canton_version=canton_version),
        method="HEAD",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return True
    except urllib.error.HTTPError as error:
        if error.code in {403, 405}:
            fallback = urllib.request.Request(
                release_url(source_config, canton_version=canton_version),
                headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
            )
            try:
                with urllib.request.urlopen(fallback, timeout=timeout):
                    return True
            except urllib.error.URLError:
                return False
        if error.code == 404:
            return False
        raise
    except urllib.error.URLError:
        return False


def latest_public_canton_bundle_version(
    source_config: LedgerApiSourceConfig,
    *,
    docs_version: str,
    repo_dir: Path = DEFAULT_REPO_DIR,
    remote: str = DEFAULT_CANTON_REMOTE,
) -> str:
    repo = canton_protobuf_history.ensure_repo(repo_dir, remote=remote, fetch=True)
    candidates = [
        version
        for version, _tag in canton_protobuf_history.stable_tags(
            repo,
            min_version=f"{docs_version}.0",
            include_versions=None,
        )
        if version.startswith(f"{docs_version}.")
    ]
    for version in reversed(candidates):
        if release_bundle_exists(source_config, canton_version=version):
            return version
    raise ValueError(f"No public Canton release bundle found for docs version {docs_version}")


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> SourceUpdate | None:
    source_config = parse_source_config(source_config_path)
    publish_entry = next(
        (entry for entry in source_config.versions if entry.version == source_config.publish_version),
        None,
    )
    if publish_entry is None:
        available = ", ".join(entry.version for entry in source_config.versions)
        raise ValueError(f"Publish version {source_config.publish_version} not found in versions: {available}")

    current_version = latest_public_canton_bundle_version(
        source_config,
        docs_version=source_config.publish_version,
    )
    if publish_entry.canton_version == current_version:
        return None

    update = SourceUpdate(
        source=SOURCE_LABEL,
        path=source_config_path,
        field=f"versions[{publish_entry.version}].canton_version",
        previous=publish_entry.canton_version,
        current=current_version,
    )
    if not dry_run:
        updated_config = dict(source_config.raw)
        updated_versions: list[dict[str, Any]] = []
        for entry in source_config.versions:
            updated_entry = dict(entry.raw)
            if entry.version == publish_entry.version:
                updated_entry["canton_version"] = current_version
            updated_versions.append(updated_entry)
        updated_config["versions"] = updated_versions
        write_json(source_config_path, updated_config)
    return update
