from __future__ import annotations

import json
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


def latest_npm_version(package_name: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    encoded_name = quote(package_name, safe="")
    request = Request(
        f"https://registry.npmjs.org/{encoded_name}",
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    latest = payload.get("dist-tags", {}).get("latest")
    if not isinstance(latest, str) or not latest:
        raise ValueError(f"npm package {package_name} does not define a latest dist-tag")
    return latest


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> list[SourceUpdate]:
    source_config = parse_source_config(source_config_path)
    updates: list[SourceUpdate] = []
    updated_packages: list[dict[str, object]] = []

    for package in source_config.packages:
        current_version = latest_npm_version(package.package_name)
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
