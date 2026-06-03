#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO_CONFIG_OUTPUT = REPO_ROOT / "config" / "repo-version-config.json"
HELPER_SCRIPT = REPO_ROOT / "scripts" / "helpers" / "updateVersionDashboardData.js"

NETWORK_ORDER = ["mainnet", "testnet", "devnet"]
RENDERED_REPOSITORY_ORDER = [
    "splice",
    "damlSdk",
    "pqs",
    "tokenStandard",
    "walletSdk",
    "dappSdk",
    "walletGateway",
]
NETWORKS = {
    "mainnet": {
        "display_name": "MainNet",
        "info_url": "https://docs.global.canton.network.sync.global/info",
        "index_url": "https://docs.global.canton.network.sync.global/index.html",
        "endpoint": "scan.sv-1.global.canton.network.sync.global",
    },
    "testnet": {
        "display_name": "TestNet",
        "info_url": "https://docs.test.global.canton.network.sync.global/info",
        "index_url": "https://docs.test.global.canton.network.sync.global/index.html",
        "endpoint": "scan.sv-1.test.global.canton.network.sync.global",
    },
    "devnet": {
        "display_name": "DevNet",
        "info_url": "https://docs.dev.global.canton.network.sync.global/info",
        "index_url": "https://docs.dev.global.canton.network.sync.global/index.html",
        "endpoint": "scan.sv-1.dev.global.canton.network.sync.global",
    },
}
NPM_PACKAGE_NAMES = {
    "tokenStandard": "@canton-network/core-token-standard",
    "walletSdk": "@canton-network/wallet-sdk",
    "dappSdk": "@canton-network/dapp-sdk",
}
NPM_PACKAGE_URLS = {
    key: f"https://www.npmjs.com/package/{package_name}"
    for key, package_name in NPM_PACKAGE_NAMES.items()
}
DPM_INSTALLER_URL = "https://get.digitalasset.com/install/install.sh"
DPM_LATEST_URL = "https://get.digitalasset.com/install/latest"
WALLET_GATEWAY_PACKAGE_URL = (
    "https://github.com/digital-asset/wallet-gateway/pkgs/container/"
    "wallet-gateway%2Fdocker%2Fwallet-gateway"
)
USER_AGENT = "cf-docs-version-dashboard-generator"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect public source data for the Canton Network version dashboard, "
            "update config/repo-version-config.json, and regenerate the dashboard snippet."
        )
    )
    parser.add_argument(
        "--repo-config-out",
        type=Path,
        default=DEFAULT_REPO_CONFIG_OUTPUT,
        help=f"Where to write the dashboard config. Default: {DEFAULT_REPO_CONFIG_OUTPUT}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Timeout in seconds for each HTTP request.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated config and do not write files.",
    )
    parser.add_argument(
        "--skip-helper",
        action="store_true",
        help="Write repo-version-config.json but do not regenerate the MDX snippet.",
    )
    return parser.parse_args()


def request_url(url: str, timeout: float):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    return urlopen(request, timeout=timeout)


def fetch_json(url: str, timeout: float) -> dict:
    with request_url(url, timeout) as response:
        return json.load(response)


def fetch_text(url: str, timeout: float) -> str:
    with request_url(url, timeout) as response:
        return response.read().decode("utf-8", "replace")


def fetch_npm_latest(package_name: str, timeout: float) -> str:
    encoded_name = package_name.replace("/", "%2F")
    data = fetch_json(f"https://registry.npmjs.org/{encoded_name}", timeout)
    return str(data["dist-tags"]["latest"])


def clean_html_text(value: str) -> str:
    value = re.sub(r"<.*?>", "", value)
    return " ".join(html.unescape(value).split())


def parse_table_pairs(page_html: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for row in re.findall(r'<tr class="row-(?:odd|even)">(.*?)</tr>', page_html, re.S):
        columns = re.findall(r"<td><p>(.*?)</p></td>", row, re.S)
        if len(columns) < 2:
            continue
        key = clean_html_text(columns[0])
        value = clean_html_text(columns[1])
        if key:
            pairs[key] = value
    return pairs


def require_value(pairs: dict[str, str], label: str, url: str) -> str:
    try:
        return pairs[label]
    except KeyError as exc:
        raise RuntimeError(f"Could not find table row {label!r} in {url}") from exc


def choose_observed_release(info_payload: dict, info_url: str) -> tuple[str, str, str]:
    sv = info_payload.get("sv", {})
    synchronizer = info_payload.get("synchronizer", {}).get("active", {})
    sv_version = sv.get("version")
    sync_version = synchronizer.get("version")
    sv_migration_id = sv.get("migration_id")
    sync_migration_id = synchronizer.get("migration_id")
    chain_id_suffix = synchronizer.get("chain_id_suffix")

    if not sv_version or not sync_version:
        raise RuntimeError(f"Missing release version in {info_url}")
    if sv_version != sync_version:
        raise RuntimeError(
            f"Version mismatch in {info_url}: "
            f"sv.version={sv_version} synchronizer.active.version={sync_version}"
        )
    if str(sv_migration_id) != str(sync_migration_id):
        raise RuntimeError(
            f"Migration mismatch in {info_url}: "
            f"sv.migration_id={sv_migration_id} synchronizer.active.migration_id={sync_migration_id}"
        )
    if chain_id_suffix is None:
        raise RuntimeError(f"Missing synchronizer.active.chain_id_suffix in {info_url}")
    return str(sv_version), str(sync_migration_id), str(chain_id_suffix)


def read_existing_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"versions": {}, "repositories": {}}


def existing_network(existing_config: dict, network_key: str) -> dict:
    return dict(existing_config.get("versions", {}).get(network_key, {}))


def existing_advanced(existing_config: dict, network_key: str) -> dict:
    return dict(existing_network(existing_config, network_key).get("advanced", {}))


def existing_repo_version(existing_config: dict, repository_key: str, network_key: str) -> str:
    repository = existing_config.get("repositories", {}).get(repository_key, {})
    mapping = repository.get("versionMapping", {}).get(network_key, {})
    return str(mapping.get("externalVersion") or "")


def updated_release_url(release_version: str) -> str:
    return f"https://github.com/canton-network/splice/releases/tag/{release_version}"


def update_substitutions(existing: dict, release_version: str) -> dict:
    substitutions = dict(existing)
    substitutions.update(
        {
            "version": release_version,
            "version_literal": release_version,
            "chart_version_literal": release_version,
            "chart_version_set": f"export CHART_VERSION={release_version}",
            "image_tag_set": f"export IMAGE_TAG={release_version}",
            "image_tag_set_plain": f"export IMAGE_TAG={release_version}",
        }
    )
    substitutions["bundle_download_link"] = {
        "label": "Download Bundle",
        "href": (
            "https://github.com/digital-asset/decentralized-canton-sync/releases/download/"
            f"v{release_version}/{release_version}_splice-node.tar.gz"
        ),
    }
    substitutions["openapi_download_link"] = {
        "label": "Download OpenAPI specs",
        "href": (
            "https://github.com/digital-asset/decentralized-canton-sync/releases/download/"
            f"v{release_version}/{release_version}_openapi.tar.gz"
        ),
    }
    return substitutions


def collect_network_snapshot(network_key: str, timeout: float) -> dict:
    urls = NETWORKS[network_key]
    info_payload = fetch_json(urls["info_url"], timeout)
    observed_release, migration_id, chain_id_suffix = choose_observed_release(
        info_payload, urls["info_url"]
    )

    index_pairs = parse_table_pairs(fetch_text(urls["index_url"], timeout))
    docker_image_tag = require_value(index_pairs, "Docker Image Tag:", urls["index_url"])
    helm_chart_version = require_value(index_pairs, "Helm Chart Version:", urls["index_url"])
    if docker_image_tag != helm_chart_version:
        raise RuntimeError(
            f"{network_key}: index page mismatch docker_image_tag={docker_image_tag} "
            f"helm_chart_version={helm_chart_version}"
        )
    if docker_image_tag != observed_release:
        raise RuntimeError(
            f"{network_key}: /info version {observed_release} does not match "
            f"docs index version {docker_image_tag}"
        )

    return {
        "displayName": urls["display_name"],
        "endpoint": urls["endpoint"],
        "spliceVersion": observed_release,
        "migrationId": migration_id,
        "chainIdSuffix": chain_id_suffix,
        "sources": {
            "infoUrl": urls["info_url"],
            "indexUrl": urls["index_url"],
        },
        "checks": {
            "dockerImageTag": docker_image_tag,
            "helmChartVersion": helm_chart_version,
        },
    }


def collect_snapshot(timeout: float) -> dict:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "generatedAt": generated_at,
        "generatorMode": "public_source_collection_with_manual_fallbacks",
        "networks": {
            network_key: collect_network_snapshot(network_key, timeout)
            for network_key in NETWORK_ORDER
        },
        "latestDpmSdk": fetch_text(DPM_LATEST_URL, timeout).strip(),
        "npmVersions": {
            key: fetch_npm_latest(package_name, timeout)
            for key, package_name in NPM_PACKAGE_NAMES.items()
        },
    }


def build_versions(existing_config: dict, snapshot: dict) -> dict:
    versions: dict[str, dict] = {}
    for network_key in NETWORK_ORDER:
        existing = existing_network(existing_config, network_key)
        existing_substitutions = existing.get("substitutions", {})
        existing_advanced_data = existing_advanced(existing_config, network_key)
        network = snapshot["networks"][network_key]

        versions[network_key] = {
            "name": network["displayName"],
            "advanced": {
                "minProtocolVersion": existing_advanced_data.get("minProtocolVersion", ""),
                "migrationId": network["migrationId"],
                "darVersions": existing_advanced_data.get("darVersions", []),
                "releaseUrl": updated_release_url(network["spliceVersion"]),
            },
            "endpoint": network["endpoint"],
            "substitutions": update_substitutions(
                existing_substitutions,
                network["spliceVersion"],
            ),
        }
    return versions


def repository_url(repository_key: str, existing_config: dict) -> str:
    existing = existing_config.get("repositories", {}).get(repository_key, {})
    if repository_key == "splice":
        return "https://github.com/canton-network/splice/releases"
    if repository_key == "walletGateway":
        return WALLET_GATEWAY_PACKAGE_URL
    if repository_key in NPM_PACKAGE_URLS:
        return NPM_PACKAGE_URLS[repository_key]
    return str(existing.get("url") or "")


def build_repository_mapping(
    repository_key: str,
    existing_config: dict,
    snapshot: dict,
) -> dict[str, dict[str, str]]:
    version_mapping: dict[str, dict[str, str]] = {}
    for network_key in NETWORK_ORDER:
        network = snapshot["networks"][network_key]
        if repository_key == "splice":
            external_version = network["spliceVersion"]
            branch = "main"
            folder_path_repo = "splice-wallet-kernel"
        elif repository_key in NPM_PACKAGE_NAMES:
            external_version = snapshot["npmVersions"][repository_key]
            branch = ""
            folder_path_repo = ""
        else:
            external_version = existing_repo_version(existing_config, repository_key, network_key)
            branch = ""
            folder_path_repo = ""

        version_mapping[network_key] = {
            "branch": branch,
            "externalVersion": external_version,
            "folderPathRepo": folder_path_repo,
        }
    return version_mapping


def build_repositories(existing_config: dict, snapshot: dict) -> dict:
    repositories: dict[str, dict] = {}
    existing_repositories = existing_config.get("repositories", {})
    repository_order = list(RENDERED_REPOSITORY_ORDER)
    for key in existing_repositories:
        if key not in repository_order:
            repository_order.append(key)

    for repository_key in repository_order:
        repositories[repository_key] = {
            "url": repository_url(repository_key, existing_config),
            "versionMapping": build_repository_mapping(
                repository_key,
                existing_config,
                snapshot,
            ),
        }
    return repositories


def build_source_contract(snapshot: dict) -> dict:
    return {
        "splice": (
            "Network /info endpoint: MainNet "
            "https://docs.global.canton.network.sync.global/info, TestNet "
            "https://docs.test.global.canton.network.sync.global/info, DevNet "
            "https://docs.dev.global.canton.network.sync.global/info. Cross-check against "
            "the same network's /index.html Docker image tag and Helm chart version."
        ),
        "canton": (
            "Manual/fallback until an owner-approved public source is confirmed. "
            "The config key remains damlSdk for compatibility with the existing dashboard component."
        ),
        "damlSdkInstaller": (
            f"DPM installer channel: curl {DPM_INSTALLER_URL} | sh; "
            f"latest stable SDK from {DPM_LATEST_URL} currently resolves to {snapshot['latestDpmSdk']}."
        ),
        "tokenStandard": f"npm latest dist-tag for {NPM_PACKAGE_NAMES['tokenStandard']}.",
        "walletSdk": f"npm latest dist-tag for {NPM_PACKAGE_NAMES['walletSdk']}.",
        "dappSdk": f"npm latest dist-tag for {NPM_PACKAGE_NAMES['dappSdk']}.",
        "walletGateway": "Manual from Wallet Gateway Docker image package until package API access is confirmed.",
        "pqs": "Manual/fallback until an owner-approved public source replaces Slack-sourced updates.",
        "minProtocolVersion": "Manual/fallback until a public live source is identified.",
        "darVersions": "Manual/fallback; release bundles list shipped DARs, not necessarily currently used DARs.",
    }


def build_config(existing_config: dict, snapshot: dict) -> dict:
    return {
        "_generated": {
            "generatedAt": snapshot["generatedAt"],
            "generatorMode": snapshot["generatorMode"],
            "sourceContract": build_source_contract(snapshot),
            "networkSources": {
                key: network["sources"] for key, network in snapshot["networks"].items()
            },
        },
        "versions": build_versions(existing_config, snapshot),
        "repositories": build_repositories(existing_config, snapshot),
    }


def without_generated_at(config: dict) -> dict:
    comparable = copy.deepcopy(config)
    generated = comparable.get("_generated")
    if isinstance(generated, dict):
        generated.pop("generatedAt", None)
    return comparable


def preserve_generated_at_if_only_timestamp_changed(existing_config: dict, candidate_config: dict) -> dict:
    existing_generated = existing_config.get("_generated")
    if not isinstance(existing_generated, dict):
        return candidate_config
    existing_generated_at = existing_generated.get("generatedAt")
    if not isinstance(existing_generated_at, str) or not existing_generated_at:
        return candidate_config
    if without_generated_at(existing_config) != without_generated_at(candidate_config):
        return candidate_config

    stable_config = copy.deepcopy(candidate_config)
    candidate_generated = stable_config.setdefault("_generated", {})
    if isinstance(candidate_generated, dict):
        candidate_generated["generatedAt"] = existing_generated_at
    return stable_config


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_helper() -> None:
    subprocess.run(["node", str(HELPER_SCRIPT)], cwd=REPO_ROOT, check=True)


def main() -> int:
    args = parse_args()
    existing_config = read_existing_config(DEFAULT_REPO_CONFIG_OUTPUT)
    snapshot = collect_snapshot(args.timeout)
    repo_version_config = preserve_generated_at_if_only_timestamp_changed(
        existing_config,
        build_config(existing_config, snapshot),
    )

    if args.dry_run:
        json.dump(repo_version_config, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    write_json(args.repo_config_out, repo_version_config)
    if not args.skip_helper:
        run_helper()

    print(f"Wrote dashboard config to {args.repo_config_out}")
    if args.skip_helper:
        print("Skipped dashboard snippet regeneration.")
    else:
        print(f"Regenerated snippet with {HELPER_SCRIPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
