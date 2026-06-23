#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path


NETWORK_LABELS = {
    "mainnet": "MainNet",
    "testnet": "TestNet",
    "devnet": "DevNet",
}

COMPONENT_LABELS = {
    "splice": "Splice",
    "damlSdk": "Canton / Daml SDK",
    "pqs": "PQS",
    "tokenStandard": "Token Standard",
    "walletSdk": "Wallet SDK",
    "dappSdk": "dApp SDK",
    "walletGateway": "Wallet Gateway",
}


def load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def object_mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return value
    return None


def object_items(value: object) -> Iterable[Mapping[str, object]]:
    if not isinstance(value, list):
        return ()
    return tuple(mapping for item in value if (mapping := object_mapping(item)) is not None)


def dar_versions(value: object) -> dict[str, object]:
    versions: dict[str, object] = {}
    for item in object_items(value):
        name = item.get("name")
        if isinstance(name, str):
            versions[name] = item.get("version")
    return versions


def format_value(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def repository_version_changes(before: Mapping[str, object], after: Mapping[str, object]) -> list[str]:
    changes: list[str] = []
    before_repositories = object_mapping(before.get("repositories"))
    after_repositories = object_mapping(after.get("repositories"))
    if before_repositories is None or after_repositories is None:
        return changes

    for component_key in sorted(after_repositories):
        before_component = object_mapping(before_repositories.get(component_key))
        after_component = object_mapping(after_repositories.get(component_key))
        if before_component is None or after_component is None:
            continue
        before_mapping = object_mapping(before_component.get("versionMapping"))
        after_mapping = object_mapping(after_component.get("versionMapping"))
        if before_mapping is None or after_mapping is None:
            continue

        component_label = COMPONENT_LABELS.get(component_key, component_key)
        for network_key in sorted(after_mapping):
            before_network = object_mapping(before_mapping.get(network_key))
            after_network = object_mapping(after_mapping.get(network_key))
            if before_network is None or after_network is None:
                continue

            before_version = before_network.get("externalVersion")
            after_version = after_network.get("externalVersion")
            if before_version != after_version:
                network_label = NETWORK_LABELS.get(network_key, network_key)
                changes.append(
                    f"- {network_label} {component_label}: "
                    f"{format_value(before_version)} -> {format_value(after_version)}"
                )
    return changes


def dar_version_changes(before: Mapping[str, object], after: Mapping[str, object]) -> list[str]:
    changes: list[str] = []
    before_versions = object_mapping(before.get("versions"))
    after_versions = object_mapping(after.get("versions"))
    if before_versions is None or after_versions is None:
        return changes

    for network_key in sorted(after_versions):
        before_network = object_mapping(before_versions.get(network_key))
        after_network = object_mapping(after_versions.get(network_key))
        if before_network is None or after_network is None:
            continue
        before_advanced = object_mapping(before_network.get("advanced"))
        after_advanced = object_mapping(after_network.get("advanced"))
        if before_advanced is None or after_advanced is None:
            continue
        before_dars = dar_versions(before_advanced.get("darVersions"))
        after_dars = dar_versions(after_advanced.get("darVersions"))
        for package_name in sorted(after_dars):
            if before_dars.get(package_name) != after_dars.get(package_name):
                network_label = NETWORK_LABELS.get(network_key, network_key)
                changes.append(
                    f"- {network_label} {package_name} DAR: "
                    f"{format_value(before_dars.get(package_name))} -> {format_value(after_dars.get(package_name))}"
                )
    return changes


def dashboard_changes(before_path: Path, after_path: Path) -> list[str]:
    before = load_json(before_path)
    after = load_json(after_path)
    return repository_version_changes(before, after) + dar_version_changes(before, after)


def source_config_changes(before_path: Path, after_path: Path, *, label: str) -> list[str]:
    before = load_json(before_path)
    after = load_json(after_path)
    changes: list[str] = []
    for field in ("publish_version", "min_version"):
        if before.get(field) != after.get(field):
            changes.append(
                f"- {label} {field}: {format_value(before.get(field))} -> {format_value(after.get(field))}"
            )
    return changes


def package_source_config_changes(before_path: Path, after_path: Path, *, label: str) -> list[str]:
    before = load_json(before_path)
    after = load_json(after_path)
    before_packages = {
        package["package_name"]: package
        for package in object_items(before.get("packages"))
        if isinstance(package.get("package_name"), str)
    }
    changes: list[str] = []
    for package in object_items(after.get("packages")):
        package_name = package.get("package_name")
        if not isinstance(package_name, str):
            continue
        before_package = before_packages.get(package_name)
        if before_package is None:
            continue
        before_version = before_package.get("publish_version")
        after_version = package.get("publish_version")
        if before_version != after_version:
            changes.append(
                f"- {label} {package_name} publish_version: "
                f"{format_value(before_version)} -> {format_value(after_version)}"
            )
    return changes


def versioned_source_config_changes(before_path: Path, after_path: Path, *, label: str) -> list[str]:
    before = load_json(before_path)
    after = load_json(after_path)
    before_versions = {
        item["version"]: item
        for item in object_items(before.get("versions"))
        if isinstance(item.get("version"), str)
    }
    changes: list[str] = []
    for item in object_items(after.get("versions")):
        version = item.get("version")
        if not isinstance(version, str):
            continue
        before_item = before_versions.get(version)
        if before_item is None:
            continue
        for field in ("canton_version",):
            if before_item.get(field) != item.get(field):
                changes.append(
                    f"- {label} {version} {field}: "
                    f"{format_value(before_item.get(field))} -> {format_value(item.get(field))}"
                )
    return changes


def artifact_source_config_changes(before_path: Path, after_path: Path, *, label: str) -> list[str]:
    before = load_json(before_path)
    after = load_json(after_path)
    before_artifacts = {
        f"{item.get('group')}:{item.get('artifact')}": item
        for item in object_items(before.get("artifacts"))
        if isinstance(item.get("group"), str) and isinstance(item.get("artifact"), str)
    }
    changes: list[str] = []
    for item in object_items(after.get("artifacts")):
        group = item.get("group")
        artifact = item.get("artifact")
        if not isinstance(group, str) or not isinstance(artifact, str):
            continue
        artifact_key = f"{group}:{artifact}"
        before_item = before_artifacts.get(artifact_key)
        if before_item is None:
            continue
        before_versions = tuple(version for version in before_item.get("versions", []) if isinstance(version, str))
        after_versions = tuple(version for version in item.get("versions", []) if isinstance(version, str))
        added_versions = [version for version in after_versions if version not in before_versions]
        if added_versions:
            changes.append(f"- {label} {artifact_key} versions: added {', '.join(added_versions)}")
    return changes


def external_snippet_source_changes(config_path: Path, *, target_key: str, label: str) -> list[str]:
    config = load_json(config_path)
    sources = object_items(config.get("sources"))
    source = next((item for item in sources if item.get("key") == target_key), None)
    if source is None:
        return []
    repository = source.get("repository")
    ref = source.get("ref")
    version = source.get("version")
    details = f"{format_value(repository)}@{format_value(ref)}"
    if version is not None:
        details += f" -> output version {format_value(version)}"
    return [f"- {label} source: {details}"]


def print_changes(changes: list[str]) -> None:
    if changes:
        print("\n".join(changes))
    else:
        print("- No version values changed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize before/after version changes as Markdown bullets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dashboard = subparsers.add_parser("dashboard", help="Summarize repo-version-config.json changes.")
    dashboard.add_argument("before", type=Path)
    dashboard.add_argument("after", type=Path)

    source_config = subparsers.add_parser("source-config", help="Summarize generated-reference source config changes.")
    source_config.add_argument("before", type=Path)
    source_config.add_argument("after", type=Path)
    source_config.add_argument("--label", required=True)
    package_source_config = subparsers.add_parser(
        "package-source-config",
        help="Summarize package-based generated-reference source config changes.",
    )
    package_source_config.add_argument("before", type=Path)
    package_source_config.add_argument("after", type=Path)
    package_source_config.add_argument("--label", required=True)
    versioned_source_config = subparsers.add_parser(
        "versioned-source-config",
        help="Summarize generated-reference source config entries keyed by docs version.",
    )
    versioned_source_config.add_argument("before", type=Path)
    versioned_source_config.add_argument("after", type=Path)
    versioned_source_config.add_argument("--label", required=True)
    artifact_source_config = subparsers.add_parser(
        "artifact-source-config",
        help="Summarize artifact-based generated-reference source config changes.",
    )
    artifact_source_config.add_argument("before", type=Path)
    artifact_source_config.add_argument("after", type=Path)
    artifact_source_config.add_argument("--label", required=True)
    external_snippet_source = subparsers.add_parser(
        "external-snippet-source",
        help="Summarize a configured external snippet source.",
    )
    external_snippet_source.add_argument("config", type=Path)
    external_snippet_source.add_argument("--target-key", required=True)
    external_snippet_source.add_argument("--label", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "dashboard":
        print_changes(dashboard_changes(args.before, args.after))
    elif args.command == "source-config":
        print_changes(source_config_changes(args.before, args.after, label=args.label))
    elif args.command == "package-source-config":
        print_changes(package_source_config_changes(args.before, args.after, label=args.label))
    elif args.command == "versioned-source-config":
        print_changes(versioned_source_config_changes(args.before, args.after, label=args.label))
    elif args.command == "artifact-source-config":
        print_changes(artifact_source_config_changes(args.before, args.after, label=args.label))
    elif args.command == "external-snippet-source":
        print_changes(
            external_snippet_source_changes(
                args.config,
                target_key=args.target_key,
                label=args.label,
            )
        )
    else:
        raise AssertionError(f"Unhandled command: {args.command}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
