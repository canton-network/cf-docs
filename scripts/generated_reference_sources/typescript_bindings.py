from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Required, TypedDict
from urllib.parse import quote
from urllib.request import Request, urlopen

from generated_reference_sources.common import SourceUpdate, load_json, write_json


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_KEY = "typescript-bindings"
SOURCE_LABEL = "TypeScript bindings"
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "typescript-bindings" / "source-artifacts.json"
DEFAULT_TIMEOUT_SECONDS = 20.0
USER_AGENT = "cf-docs-generated-reference-source-updater"
STABLE_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class TypeScriptPackageConfigPayload(TypedDict, total=False):
    package_name: Required[str]
    source: str
    version_filter: str
    page_title: str
    page_description: str
    output_file: str
    entry_point: str
    typedoc_args: list[str]
    typedoc_version: str
    publish_version: Required[str]
    versions: Required[list[str]]


@dataclass(frozen=True)
class TypeScriptPackageConfig:
    raw: TypeScriptPackageConfigPayload
    package_name: str
    publish_version: str
    versions: tuple[str, ...]


@dataclass(frozen=True)
class TypeScriptBindingsSourceConfig:
    raw: dict[str, object]
    packages: tuple[TypeScriptPackageConfig, ...]


def parse_source_config(path: Path) -> TypeScriptBindingsSourceConfig:
    raw_json = load_json(path)
    packages_json = raw_json.get("packages")
    if not isinstance(packages_json, list) or not packages_json:
        raise ValueError(f"{path} must define a non-empty packages list")

    packages: list[TypeScriptPackageConfig] = []
    for index, package_json in enumerate(packages_json):
        if not isinstance(package_json, dict):
            raise ValueError(f"{path} packages[{index}] must be an object")
        package_name = package_json.get("package_name")
        publish_version = package_json.get("publish_version")
        versions = package_json.get("versions")
        if not isinstance(package_name, str) or not package_name:
            raise ValueError(f"{path} packages[{index}] must define package_name")
        if not isinstance(publish_version, str) or not publish_version:
            raise ValueError(f"{path} packages[{package_name}] must define publish_version")
        if not isinstance(versions, list) or not all(isinstance(version, str) and version for version in versions):
            raise ValueError(f"{path} packages[{package_name}] must define a non-empty versions string list")

        raw: TypeScriptPackageConfigPayload = {}
        raw.update(package_json)
        packages.append(
            TypeScriptPackageConfig(
                raw=raw,
                package_name=package_name,
                publish_version=publish_version,
                versions=tuple(versions),
            )
        )
    return TypeScriptBindingsSourceConfig(raw=raw_json, packages=tuple(packages))


def version_key(version: str) -> tuple[int, int, int]:
    if not STABLE_SEMVER_RE.fullmatch(version):
        raise ValueError(f"Expected stable semantic version, got {version!r}")
    major, minor, patch = version.split(".")
    return (int(major), int(minor), int(patch))


def highest_stable_npm_version(package_name: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    encoded_name = quote(package_name, safe="")
    request = Request(
        f"https://registry.npmjs.org/{encoded_name}",
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    # npm's latest tag follows publication order and can move to an older maintained major line.
    versions = payload.get("versions")
    if not isinstance(versions, dict):
        raise ValueError(f"npm package {package_name} does not define a versions object")
    stable_versions = [
        version
        for version in versions
        if isinstance(version, str) and STABLE_SEMVER_RE.fullmatch(version)
    ]
    if not stable_versions:
        raise ValueError(f"npm package {package_name} does not define any stable semantic versions")
    return max(stable_versions, key=version_key)


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> list[SourceUpdate]:
    source_config = parse_source_config(source_config_path)
    updates: list[SourceUpdate] = []
    updated_packages: list[dict[str, object]] = []

    for package in source_config.packages:
        current_version = highest_stable_npm_version(package.package_name)
        updated_package = dict(package.raw)
        if package.publish_version != current_version:
            updates.append(
                SourceUpdate(
                    source=f"{SOURCE_LABEL} {package.package_name}",
                    path=source_config_path,
                    field="publish_version",
                    previous=package.publish_version,
                    current=current_version,
                )
            )
            versions = list(package.versions)
            if current_version not in versions:
                versions.append(current_version)
            updated_package["publish_version"] = current_version
            updated_package["versions"] = versions
        updated_packages.append(updated_package)

    if updates and not dry_run:
        updated_config = dict(source_config.raw)
        updated_config["packages"] = updated_packages
        write_json(source_config_path, updated_config)
    return updates
