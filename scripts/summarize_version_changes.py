#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


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


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def format_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def repository_version_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    before_repositories = before.get("repositories")
    after_repositories = after.get("repositories")
    if not isinstance(before_repositories, dict) or not isinstance(after_repositories, dict):
        return changes

    for component_key in sorted(after_repositories):
        before_component = before_repositories.get(component_key)
        after_component = after_repositories.get(component_key)
        if not isinstance(before_component, dict) or not isinstance(after_component, dict):
            continue
        before_mapping = before_component.get("versionMapping")
        after_mapping = after_component.get("versionMapping")
        if not isinstance(before_mapping, dict) or not isinstance(after_mapping, dict):
            continue

        component_label = COMPONENT_LABELS.get(component_key, component_key)
        for network_key in sorted(after_mapping):
            before_network = before_mapping.get(network_key)
            after_network = after_mapping.get(network_key)
            if not isinstance(before_network, dict) or not isinstance(after_network, dict):
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


def dar_version_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    before_versions = before.get("versions")
    after_versions = after.get("versions")
    if not isinstance(before_versions, dict) or not isinstance(after_versions, dict):
        return changes

    for network_key in sorted(after_versions):
        before_network = before_versions.get(network_key)
        after_network = after_versions.get(network_key)
        if not isinstance(before_network, dict) or not isinstance(after_network, dict):
            continue
        before_advanced = before_network.get("advanced")
        after_advanced = after_network.get("advanced")
        if not isinstance(before_advanced, dict) or not isinstance(after_advanced, dict):
            continue
        before_dars = {
            item.get("name"): item.get("version")
            for item in before_advanced.get("darVersions", [])
            if isinstance(item, dict)
        }
        after_dars = {
            item.get("name"): item.get("version")
            for item in after_advanced.get("darVersions", [])
            if isinstance(item, dict)
        }
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "dashboard":
        print_changes(dashboard_changes(args.before, args.after))
    elif args.command == "source-config":
        print_changes(source_config_changes(args.before, args.after, label=args.label))
    else:
        raise AssertionError(f"Unhandled command: {args.command}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
