from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import generate_canton_protobuf_history as canton_protobuf_history

from generate_canton_protobuf_history import semver_key
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


STABLE_BUNDLE_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def release_line(version: str) -> str:
    major, minor, *_rest = version.split(".")
    return f"{major}.{minor}"


def line_key(line: str) -> tuple[int, int]:
    major, minor = line.split(".")
    return (int(major), int(minor))


def latest_public_canton_bundle_versions(
    source_config: LedgerApiSourceConfig,
    *,
    min_line: str,
    repo_dir: Path = DEFAULT_REPO_DIR,
    remote: str = DEFAULT_CANTON_REMOTE,
) -> dict[str, str]:
    """Return the newest stable Canton release with a public bundle for each release line.

    Lines older than ``min_line`` are ignored. A line with no public bundle is omitted.
    """
    repo = canton_protobuf_history.ensure_repo(repo_dir, remote=remote, fetch=True)
    versions_by_line: dict[str, list[str]] = {}
    for version, _tag in canton_protobuf_history.stable_tags(
        repo,
        min_version=f"{min_line}.0",
        include_versions=None,
    ):
        versions_by_line.setdefault(release_line(version), []).append(version)

    latest_by_line: dict[str, str] = {}
    for line, versions in versions_by_line.items():
        for version in reversed(versions):
            if release_bundle_exists(source_config, canton_version=version):
                latest_by_line[line] = version
                break
    return latest_by_line


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> list[SourceUpdate]:
    """Keep the JSON Ledger API pins on the newest public Canton releases.

    - Every release line pinned to a stable release moves to that line's latest public patch.
      Snapshot pins are deliberate and are left alone.
    - Release lines newer than any configured line are added once a public bundle exists.
    - ``publish_version`` always names the newest configured line.
    """
    source_config = parse_source_config(source_config_path)
    configured_lines = [entry.version for entry in source_config.versions]
    latest_by_line = latest_public_canton_bundle_versions(
        source_config,
        min_line=min(configured_lines, key=line_key),
    )

    updates: list[SourceUpdate] = []
    updated_versions: list[dict[str, Any]] = []
    for entry in source_config.versions:
        updated_entry = dict(entry.raw)
        latest = latest_by_line.get(entry.version)
        if (
            latest is not None
            and STABLE_BUNDLE_VERSION_RE.fullmatch(entry.canton_version)
            and semver_key(latest) > semver_key(entry.canton_version)
        ):
            updated_entry["canton_version"] = latest
            updates.append(
                SourceUpdate(
                    source=SOURCE_LABEL,
                    path=source_config_path,
                    field=f"versions[{entry.version}].canton_version",
                    previous=entry.canton_version,
                    current=latest,
                )
            )
        updated_versions.append(updated_entry)

    newest_configured = max(configured_lines, key=line_key)
    for line in sorted(latest_by_line, key=line_key):
        if line_key(line) <= line_key(newest_configured):
            continue
        updated_versions.append({"version": line, "canton_version": latest_by_line[line]})
        updates.append(
            SourceUpdate(
                source=SOURCE_LABEL,
                path=source_config_path,
                field=f"versions[{line}]",
                previous="(not configured)",
                current=latest_by_line[line],
            )
        )

    publish_version = max((entry["version"] for entry in updated_versions), key=line_key)
    if publish_version != source_config.publish_version:
        updates.append(
            SourceUpdate(
                source=SOURCE_LABEL,
                path=source_config_path,
                field="publish_version",
                previous=source_config.publish_version,
                current=publish_version,
            )
        )

    if updates and not dry_run:
        updated_config = dict(source_config.raw)
        updated_config["versions"] = updated_versions
        updated_config["publish_version"] = publish_version
        write_json(source_config_path, updated_config)
    return updates
