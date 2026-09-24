#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve a component version from an installed DPM SDK manifest."
    )
    parser.add_argument("--dpm-home", required=True)
    parser.add_argument("--sdk-version", required=True)
    parser.add_argument("--component", required=True)
    return parser.parse_args()


def resolve_component_version(
    *, dpm_home: Path, sdk_version: str, component: str
) -> str:
    manifest_root = dpm_home / "cache" / "sdk"
    manifest_paths = sorted(
        [
            *manifest_root.glob(f"*/{sdk_version}.yaml"),
            *manifest_root.glob(f"*/{sdk_version}.yml"),
        ]
    )
    if not manifest_paths:
        raise ValueError(
            f"No installed DPM SDK manifest found for {sdk_version} under {manifest_root}"
        )

    versions: set[str] = set()
    for manifest_path in manifest_paths:
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(
                f"Expected YAML object in DPM SDK manifest: {manifest_path}"
            )
        spec = payload.get("spec")
        components = spec.get("components") if isinstance(spec, dict) else None
        component_config = (
            components.get(component) if isinstance(components, dict) else None
        )
        version = (
            component_config.get("version")
            if isinstance(component_config, dict)
            else None
        )
        if isinstance(version, str) and version:
            versions.add(version)

    if not versions:
        manifests = ", ".join(str(path) for path in manifest_paths)
        raise ValueError(
            f"DPM SDK {sdk_version} does not define component {component!r} in: {manifests}"
        )
    if len(versions) > 1:
        rendered_versions = ", ".join(sorted(versions))
        raise ValueError(
            f"DPM SDK {sdk_version} maps component {component!r} to multiple versions: {rendered_versions}"
        )
    return versions.pop()


def main() -> int:
    args = parse_args()
    try:
        print(
            resolve_component_version(
                dpm_home=Path(args.dpm_home).expanduser(),
                sdk_version=args.sdk_version,
                component=args.component,
            )
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
