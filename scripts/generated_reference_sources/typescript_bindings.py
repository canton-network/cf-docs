from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from generated_reference_sources.common import SourceUpdate, load_json


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_KEY = "typescript-bindings"
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "typescript-bindings" / "source-artifacts.json"
DEFAULT_TIMEOUT_SECONDS = 20.0
USER_AGENT = "cf-docs-generated-reference-source-updater"
STABLE_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class TypeScriptPackageConfig:
    package_name: str
    min_version: str


@dataclass(frozen=True)
class TypeScriptBindingsSourceConfig:
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
        min_version = package_json.get("min_version")
        if not isinstance(package_name, str) or not package_name:
            raise ValueError(f"{path} packages[{index}] must define package_name")
        if not isinstance(min_version, str) or not min_version:
            raise ValueError(f"{path} packages[{package_name}] must define min_version")
        version_key(min_version)

        packages.append(
            TypeScriptPackageConfig(
                package_name=package_name,
                min_version=min_version,
            )
        )
    return TypeScriptBindingsSourceConfig(packages=tuple(packages))


def version_key(version: str) -> tuple[int, int, int]:
    if not STABLE_SEMVER_RE.fullmatch(version):
        raise ValueError(f"Expected stable semantic version, got {version!r}")
    major, minor, patch = version.split(".")
    return (int(major), int(minor), int(patch))


def stable_npm_versions(package_name: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> tuple[str, ...]:
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
    return tuple(sorted(stable_versions, key=version_key))


def highest_stable_npm_version(package_name: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    return stable_npm_versions(package_name, timeout=timeout)[-1]


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> list[SourceUpdate]:
    # TypeScript history is intentionally unbounded: generation discovers every
    # stable npm release at or above each package's configured lower bound and
    # publishes the latest selected release. Keep this compatibility updater as a
    # validating no-op so callers never have to extend a checked-in version list.
    _ = dry_run
    parse_source_config(source_config_path)
    return []
