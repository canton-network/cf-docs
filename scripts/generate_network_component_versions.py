#!/usr/bin/env python3

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from urllib.error import HTTPError
from pathlib import Path
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO_CONFIG_OUTPUT = REPO_ROOT / "config" / "repo-version-config.json"
HELPER_SCRIPT = REPO_ROOT / "scripts" / "helpers" / "updateVersionDashboardData.js"

NETWORK_ORDER = ["mainnet", "testnet", "devnet"]
REPOSITORY_ORDER = [
    "splice",
    "damlSdk",
    "pqs",
    "tokenStandard",
    "walletSdk",
    "dappSdk",
    "walletGateway",
]
DAR_ORDER = [
    "splice-amulet",
    "splice-amulet-name-service",
    "splice-dso-governance",
    "splice-validator-lifecycle",
    "splice-wallet",
    "splice-wallet-payments",
]
NETWORKS = {
    "mainnet": {
        "display_name": "MainNet",
        "info_url": "https://docs.global.canton.network.sync.global/info",
        "index_url": "https://docs.global.canton.network.sync.global/index.html",
        "version_info_url": "https://docs.global.canton.network.sync.global/app_dev/overview/version_information.html",
        "release_notes_url": "https://docs.global.canton.network.sync.global/release_notes.html",
        "endpoint": "scan.sv-1.global.canton.network.sync.global",
    },
    "testnet": {
        "display_name": "TestNet",
        "info_url": "https://docs.test.global.canton.network.sync.global/info",
        "index_url": "https://docs.test.global.canton.network.sync.global/index.html",
        "version_info_url": "https://docs.test.global.canton.network.sync.global/app_dev/overview/version_information.html",
        "release_notes_url": "https://docs.test.global.canton.network.sync.global/release_notes.html",
        "endpoint": "scan.sv-1.test.global.canton.network.sync.global",
    },
    "devnet": {
        "display_name": "DevNet",
        "info_url": "https://docs.dev.global.canton.network.sync.global/info",
        "index_url": "https://docs.dev.global.canton.network.sync.global/index.html",
        "version_info_url": "https://docs.dev.global.canton.network.sync.global/app_dev/overview/version_information.html",
        "release_notes_url": "https://docs.dev.global.canton.network.sync.global/release_notes.html",
        "endpoint": "scan.sv-1.dev.global.canton.network.sync.global",
    },
}
PACKAGE_SOURCES = {
    "tokenStandard": "https://www.npmjs.com/package/@canton-network/core-token-standard",
    "walletSdk": "https://www.npmjs.com/package/@canton-network/wallet-sdk",
    "dappSdk": "https://www.npmjs.com/package/@canton-network/dapp-sdk",
    "walletGateway": "https://www.npmjs.com/package/@canton-network/wallet-gateway-remote",
}
PACKAGE_NAMES = {
    "tokenStandard": "@canton-network/core-token-standard",
    "walletSdk": "@canton-network/wallet-sdk",
    "dappSdk": "@canton-network/dapp-sdk",
    "walletGateway": "@canton-network/wallet-gateway-remote",
}
PQS_DOC_URL_TEMPLATE = "https://docs.digitalasset.com/build/{doc_version}/component-howtos/pqs/download.html"
PQS_DIRECT_VERSION_PATTERNS = [
    re.compile(r"participant-query-store:(\d+\.\d+\.\d+)"),
    re.compile(r"`dpm install (\d+\.\d+\.\d+)`"),
]
DEFAULT_MIN_PROTOCOL_VERSION = "6"
USER_AGENT = "canton-network-version-dashboard-generator"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Canton Network version dashboard source data, rewrite "
            "config/repo-version-config.json, and regenerate the published MDX snippet."
        )
    )
    parser.add_argument(
        "--repo-config-out",
        type=Path,
        default=DEFAULT_REPO_CONFIG_OUTPUT,
        help=f"Where to write the legacy dashboard config. Default: {DEFAULT_REPO_CONFIG_OUTPUT}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Timeout in seconds for each HTTP request.",
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


def choose_observed_release(info_payload: dict, info_url: str) -> tuple[str, str]:
    sv = info_payload.get("sv", {})
    synchronizer = info_payload.get("synchronizer", {}).get("active", {})
    sv_version = sv.get("version")
    sync_version = synchronizer.get("version")
    sv_migration_id = sv.get("migration_id")
    sync_migration_id = synchronizer.get("migration_id")

    if not sv_version or not sync_version:
        raise RuntimeError(f"Missing release version in {info_url}")
    if sv_version != sync_version:
        raise RuntimeError(
            f"Version mismatch in {info_url}: sv.version={sv_version} synchronizer.active.version={sync_version}"
        )
    if str(sv_migration_id) != str(sync_migration_id):
        raise RuntimeError(
            f"Migration mismatch in {info_url}: sv.migration_id={sv_migration_id} "
            f"synchronizer.active.migration_id={sync_migration_id}"
        )
    return sv_version, str(sync_migration_id)


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def parse_canton_minor_version(canton_version: str) -> str:
    match = re.match(r"^(\d+\.\d+)", canton_version)
    if not match:
        raise RuntimeError(f"Could not determine Canton major.minor version from {canton_version!r}")
    return match.group(1)


def parse_release_bundle_url(release_notes_html: str, release_version: str, release_notes_url: str) -> str:
    release_id = release_version.replace(".", "-")
    section_match = re.search(
        rf'<span id="id-{re.escape(release_id)}"></span><h1>{re.escape(release_version)}.*?</section>',
        release_notes_html,
        re.S,
    )
    link_pattern = re.compile(
        rf'<a class="reference external" href="([^"]+)">Download release bundle for version {re.escape(release_version)}</a>'
    )
    if section_match:
        href_match = link_pattern.search(section_match.group(0))
        if href_match:
            return html.unescape(href_match.group(1))

    fallback = link_pattern.search(release_notes_html)
    if fallback:
        return html.unescape(fallback.group(1))

    raise RuntimeError(f"Could not find release bundle link for {release_version} in {release_notes_url}")


def extract_dar_versions(release_bundle_url: str, timeout: float) -> list[dict[str, str]]:
    discovered: dict[str, str] = {}
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as bundle_file:
        bundle_path = Path(bundle_file.name)
        with request_url(release_bundle_url, timeout) as response:
            shutil.copyfileobj(response, bundle_file)

    try:
        with tarfile.open(bundle_path, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                match = re.search(r"(^|/)([^/]+)-(\d+\.\d+\.\d+)\.dar$", member.name)
                if not match:
                    continue
                dar_name = match.group(2)
                dar_version = match.group(3)
                if dar_name not in DAR_ORDER:
                    continue
                current = discovered.get(dar_name)
                if current is None or version_key(dar_version) > version_key(current):
                    discovered[dar_name] = dar_version
    finally:
        bundle_path.unlink(missing_ok=True)

    return [
        {"name": dar_name, "version": discovered[dar_name]}
        for dar_name in DAR_ORDER
        if dar_name in discovered
    ]


def fetch_package_version(package_name: str, timeout: float) -> dict[str, str]:
    encoded_name = package_name.replace("/", "%2F")
    url = f"https://registry.npmjs.org/{encoded_name}"
    data = fetch_json(url, timeout)
    latest = data["dist-tags"]["latest"]
    return {
        "package": package_name,
        "version": latest,
        "url": url,
    }


def parse_pqs_direct_version(page_html: str, source_url: str) -> str:
    for pattern in PQS_DIRECT_VERSION_PATTERNS:
        match = pattern.search(page_html)
        if match:
            return match.group(1)
    raise RuntimeError(f"Could not find a direct PQS version example in {source_url}")


def parse_pqs_compatibility_versions(page_html: str, source_url: str) -> list[str]:
    pairs = parse_table_pairs(page_html)
    versions = pairs.get("Canton Participant Node")
    if not versions:
        raise RuntimeError(f"Could not find PQS compatibility table entry for Canton Participant Node in {source_url}")
    return [item.strip() for item in versions.split(",") if item.strip()]


def candidate_pqs_doc_versions(canton_minor_version: str) -> list[str]:
    major, minor = (int(part) for part in canton_minor_version.split("."))
    candidates = []
    for delta in (2, 1, 0, -1):
        candidate_minor = minor + delta
        if candidate_minor < 0:
            continue
        candidates.append(f"{major}.{candidate_minor}")
    seen = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)
    return ordered


def fetch_recommended_pqs_version(
    canton_version: str,
    timeout: float,
    cache: dict[str, dict[str, object]],
) -> dict[str, object]:
    canton_minor = parse_canton_minor_version(canton_version)
    if canton_minor in cache:
        return cache[canton_minor]

    compatible_candidates: list[dict[str, object]] = []
    for doc_version in candidate_pqs_doc_versions(canton_minor):
        source_url = PQS_DOC_URL_TEMPLATE.format(doc_version=doc_version)
        try:
            page_html = fetch_text(source_url, timeout)
        except HTTPError as exc:
            if exc.code == 404:
                continue
            raise

        direct_version = parse_pqs_direct_version(page_html, source_url)
        compatibility_versions = parse_pqs_compatibility_versions(page_html, source_url)
        if canton_minor not in compatibility_versions:
            continue

        compatible_candidates.append(
            {
                "version": direct_version,
                "url": source_url,
                "compatibleCantonVersions": compatibility_versions,
                "sourceDocVersion": doc_version,
            }
        )

    if not compatible_candidates:
        raise RuntimeError(
            f"Could not find a PQS docs page whose compatibility table lists Canton {canton_minor}"
        )

    recommendation = max(
        compatible_candidates,
        key=lambda candidate: version_key(str(candidate["version"])),
    )
    cache[canton_minor] = recommendation
    return recommendation


def release_notes_anchor(base_url: str, release_version: str) -> str:
    return f"{base_url}#id-{release_version.replace('.', '-')}"


def build_network_snapshot(
    network_key: str,
    timeout: float,
    package_versions: dict[str, dict[str, str]],
    pqs_recommendation_cache: dict[str, dict[str, object]],
    release_bundle_cache: dict[str, list[dict[str, str]]],
) -> dict:
    urls = NETWORKS[network_key]
    info_payload = fetch_json(urls["info_url"], timeout)
    observed_release, migration_id = choose_observed_release(info_payload, urls["info_url"])

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
            f"{network_key}: /info version {observed_release} does not match docs index version {docker_image_tag}"
        )

    version_pairs = parse_table_pairs(fetch_text(urls["version_info_url"], timeout))
    canton_version = require_value(
        version_pairs,
        "Canton version used for validator and SV nodes",
        urls["version_info_url"],
    )
    daml_sdk_version = require_value(
        version_pairs,
        "Daml SDK version used to compile .dars",
        urls["version_info_url"],
    )
    daml_codegen_sdk_version = require_value(
        version_pairs,
        "Daml SDK version used for Java and TS codegens",
        urls["version_info_url"],
    )
    pqs_recommendation = fetch_recommended_pqs_version(canton_version, timeout, pqs_recommendation_cache)

    release_notes_html = fetch_text(urls["release_notes_url"], timeout)
    bundle_url = parse_release_bundle_url(release_notes_html, observed_release, urls["release_notes_url"])
    if bundle_url not in release_bundle_cache:
        release_bundle_cache[bundle_url] = extract_dar_versions(bundle_url, timeout)

    notes: list[str] = []
    notes.append(
        "minProtocolVersion uses the previous checked-in value because the live network docs do not expose a public source for it."
    )
    notes.append(
        f"PQS is recommended from the highest PQS docs version whose compatibility table lists Canton {parse_canton_minor_version(canton_version)}."
    )

    return {
        "displayName": urls["display_name"],
        "endpoint": urls["endpoint"],
        "sources": {
            "infoUrl": urls["info_url"],
            "indexUrl": urls["index_url"],
            "versionInfoUrl": urls["version_info_url"],
            "releaseNotesUrl": urls["release_notes_url"],
            "releaseBundleUrl": bundle_url,
        },
        "components": {
            "splice": {
                "version": observed_release,
                "source": {
                    "kind": "docs_info",
                    "url": urls["info_url"],
                },
            },
            "damlSdk": {
                "version": daml_sdk_version,
                "source": {
                    "kind": "docs_version_information",
                    "url": urls["version_info_url"],
                },
            },
            "pqs": {
                "version": str(pqs_recommendation["version"]),
                "source": {
                    "kind": "digital_asset_docs",
                    "url": str(pqs_recommendation["url"]),
                    "note": (
                        f"Recommended because this PQS docs page lists Canton {parse_canton_minor_version(canton_version)} "
                        f"as compatible (tested versions: {', '.join(pqs_recommendation['compatibleCantonVersions'])})."
                    ),
                    "compatibleCantonVersions": list(pqs_recommendation["compatibleCantonVersions"]),
                },
            },
            "tokenStandard": {
                "version": package_versions["tokenStandard"]["version"],
                "source": {
                    "kind": "npm_registry",
                    "url": PACKAGE_SOURCES["tokenStandard"],
                    "package": package_versions["tokenStandard"]["package"],
                },
            },
            "walletSdk": {
                "version": package_versions["walletSdk"]["version"],
                "source": {
                    "kind": "npm_registry",
                    "url": PACKAGE_SOURCES["walletSdk"],
                    "package": package_versions["walletSdk"]["package"],
                },
            },
            "dappSdk": {
                "version": package_versions["dappSdk"]["version"],
                "source": {
                    "kind": "npm_registry",
                    "url": PACKAGE_SOURCES["dappSdk"],
                    "package": package_versions["dappSdk"]["package"],
                },
            },
            "walletGateway": {
                "version": package_versions["walletGateway"]["version"],
                "source": {
                    "kind": "npm_registry",
                    "url": PACKAGE_SOURCES["walletGateway"],
                    "package": package_versions["walletGateway"]["package"],
                },
            },
        },
        "advanced": {
            "minProtocolVersion": {
                "value": DEFAULT_MIN_PROTOCOL_VERSION,
                "status": "fallback",
                "note": notes[0],
            },
            "migrationId": {
                "value": migration_id,
                "source": {
                    "kind": "docs_info",
                    "url": urls["info_url"],
                },
            },
            "chainIdSuffix": {
                "value": info_payload["synchronizer"]["active"]["chain_id_suffix"],
                "source": {
                    "kind": "docs_info",
                    "url": urls["info_url"],
                },
            },
            "darVersions": [
                {
                    "name": dar["name"],
                    "version": dar["version"],
                    "source": {
                        "kind": "release_bundle",
                        "url": bundle_url,
                        "note": "Highest versioned DAR discovered in the published release bundle.",
                    },
                }
                for dar in release_bundle_cache[bundle_url]
            ],
            "releaseUrl": release_notes_anchor(urls["release_notes_url"], observed_release),
        },
        "docsChecks": {
            "dockerImageTag": docker_image_tag,
            "helmChartVersion": helm_chart_version,
            "canton": canton_version,
            "damlSdk": daml_sdk_version,
            "damlCodegenSdk": daml_codegen_sdk_version,
        },
        "notes": notes,
    }


def human_timestamp(raw_timestamp: str) -> str:
    timestamp = datetime.fromisoformat(raw_timestamp)
    return timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_snapshot(timeout: float) -> dict:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    release_bundle_cache: dict[str, list[dict[str, str]]] = {}
    package_versions = {
        key: fetch_package_version(package_name, timeout)
        for key, package_name in PACKAGE_NAMES.items()
    }
    pqs_recommendation_cache: dict[str, dict[str, object]] = {}

    return {
        "generatedAt": generated_at,
        "generatedAtDisplay": human_timestamp(generated_at),
        "generatorMode": "legacy_dashboard_pipeline",
        "summary": [
            "Core network versions come from live Canton Network docs.",
            "DAR versions come from the published splice-node release bundle for the observed network release.",
            "walletSdk, dappSdk, walletGateway, and tokenStandard come from their published npm packages.",
            "PQS is recommended from the highest PQS docs version whose compatibility table lists the network's current Canton major.minor version.",
            "minProtocolVersion is carried forward as a fallback because no public live source was identified.",
        ],
        "networks": {
            network_key: build_network_snapshot(
                network_key,
                timeout,
                package_versions,
                pqs_recommendation_cache,
                release_bundle_cache,
            )
            for network_key in NETWORK_ORDER
        },
    }


def build_repo_version_config(snapshot: dict) -> dict:
    versions: dict[str, dict] = {}
    for network_key in NETWORK_ORDER:
        network = snapshot["networks"][network_key]
        versions[network_key] = {
            "name": network["displayName"],
            "advanced": {
                "minProtocolVersion": network["advanced"]["minProtocolVersion"]["value"],
                "migrationId": network["advanced"]["migrationId"]["value"],
                "darVersions": [
                    {"name": dar["name"], "version": dar["version"]}
                    for dar in network["advanced"]["darVersions"]
                ],
                "releaseUrl": network["advanced"]["releaseUrl"],
            },
            "endpoint": network["endpoint"],
        }

    repositories: dict[str, dict] = {}
    repository_urls = {
        "splice": "https://docs.global.canton.network.sync.global/release_notes.html",
        "damlSdk": "https://github.com/digital-asset/daml/releases",
        "pqs": snapshot["networks"]["mainnet"]["components"]["pqs"]["source"]["url"],
        "tokenStandard": PACKAGE_SOURCES["tokenStandard"],
        "walletSdk": PACKAGE_SOURCES["walletSdk"],
        "dappSdk": PACKAGE_SOURCES["dappSdk"],
        "walletGateway": PACKAGE_SOURCES["walletGateway"],
    }
    for repository_key in REPOSITORY_ORDER:
        version_mapping: dict[str, dict[str, str]] = {}
        for network_key in NETWORK_ORDER:
            component = snapshot["networks"][network_key]["components"][repository_key]
            branch = "main" if repository_key == "splice" else ""
            folder_path_repo = "splice-wallet-kernel" if repository_key == "splice" else ""
            version_mapping[network_key] = {
                "branch": branch,
                "externalVersion": component["version"],
                "folderPathRepo": folder_path_repo,
            }
        repositories[repository_key] = {
            "url": repository_urls[repository_key],
            "versionMapping": version_mapping,
        }

    return {
        "_generated": {
            "generatedAt": snapshot["generatedAt"],
            "generatedAtDisplay": snapshot["generatedAtDisplay"],
            "summary": snapshot["summary"],
        },
        "versions": versions,
        "repositories": repositories,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_helper() -> None:
    subprocess.run(["node", str(HELPER_SCRIPT)], cwd=REPO_ROOT, check=True)


def main() -> int:
    args = parse_args()
    snapshot = build_snapshot(args.timeout)
    repo_version_config = build_repo_version_config(snapshot)

    write_json(args.repo_config_out, repo_version_config)
    run_helper()

    print(f"Wrote dashboard config to {args.repo_config_out}")
    print(f"Regenerated snippet with {HELPER_SCRIPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
