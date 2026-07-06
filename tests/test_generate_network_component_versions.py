from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from urllib.parse import parse_qs, urlparse

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "generate_network_component_versions.py"
    scripts_dir = str(script_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[script_path.stem] = module
    spec.loader.exec_module(module)
    return module


def dashboard_snapshot(*, generated_at: str, splice_version: str) -> dict:
    networks = {}
    for network_key, display_name in [
        ("mainnet", "MainNet"),
        ("testnet", "TestNet"),
        ("devnet", "DevNet"),
    ]:
        networks[network_key] = {
            "sources": {"infoUrl": f"https://example.com/{network_key}/info"},
            "displayName": display_name,
            "migrationId": "1",
            "spliceVersion": splice_version,
            "endpoint": f"scan.{network_key}.example",
            "cantonVersion": "3.5.1",
            "cantonReleaseLineBranch": "release-line-0.6",
            "darVersions": [],
        }

    return {
        "generatedAt": generated_at,
        "generatorMode": "public_source_collection_with_manual_fallbacks",
        "networks": networks,
        "latestDpmSdk": "3.5.1",
        "latestPqs": "3.5.1",
        "latestWalletGateway": "1.4.0",
        "npmVersions": {
            "tokenStandard": "1.4.0",
            "walletSdk": "1.4.0",
            "dappSdk": "1.1.0",
        },
    }


def test_build_config_preserves_generated_at_when_only_timestamp_changes() -> None:
    module = load_script_module()
    existing_config = module.build_config(
        {"versions": {}, "repositories": {}},
        dashboard_snapshot(
            generated_at="2026-06-01T00:00:00+00:00",
            splice_version="0.6.3",
        ),
    )

    result = module.build_config(
        existing_config,
        dashboard_snapshot(
            generated_at="2026-06-03T12:00:00+00:00",
            splice_version="0.6.3",
        ),
    )

    assert result["_generated"]["generatedAt"] == "2026-06-01T00:00:00+00:00"


def test_build_config_keeps_new_generated_at_when_dashboard_data_changes() -> None:
    module = load_script_module()
    existing_config = module.build_config(
        {"versions": {}, "repositories": {}},
        dashboard_snapshot(generated_at="2026-06-01T00:00:00+00:00", splice_version="0.6.2"),
    )

    result = module.build_config(
        existing_config,
        dashboard_snapshot(generated_at="2026-06-03T12:00:00+00:00", splice_version="0.6.3"),
    )

    assert result["_generated"]["generatedAt"] == "2026-06-03T12:00:00+00:00"


def test_choose_observed_release_accepts_active_synchronizer_payload() -> None:
    module = load_script_module()

    assert module.choose_observed_release(
        {
            "sv": {"migration_id": 4, "version": "0.6.5"},
            "synchronizer": {
                "active": {
                    "chain_id_suffix": "2",
                    "migration_id": 4,
                    "version": "0.6.5",
                }
            },
        },
        "https://example.com/info",
    ) == ("0.6.5", "4", "2")


def test_choose_observed_release_accepts_current_synchronizer_payload() -> None:
    module = load_script_module()

    assert module.choose_observed_release(
        {
            "sv": {"migration_id": 1, "serial_id": 2, "version": "0.6.7"},
            "synchronizer": {
                "current": {
                    "chain_id_suffix": "6",
                    "serial_id": 2,
                    "version": "0.6.7",
                },
                "legacy": {
                    "chain_id_suffix": "6",
                    "serial_id": 1,
                    "version": "0.6.6",
                },
            },
        },
        "https://example.com/info",
    ) == ("0.6.7", "1", "6")


def test_choose_observed_release_rejects_version_mismatch() -> None:
    module = load_script_module()

    with pytest.raises(RuntimeError, match="Version mismatch"):
        module.choose_observed_release(
            {
                "sv": {"migration_id": 1, "version": "0.6.7"},
                "synchronizer": {
                    "current": {
                        "chain_id_suffix": "6",
                        "version": "0.6.6",
                    }
                },
            },
            "https://example.com/info",
        )


def test_latest_stable_version_ignores_prerelease_and_debug_tags() -> None:
    module = load_script_module()

    assert (
        module.latest_stable_version(
            [
                "3.4.6",
                "3.5.1-rc7",
                "3.5.1-rc7-debug",
                "3.5.1",
                "3.5.1-debug",
            ],
            "test",
        )
        == "3.5.1"
    )


def test_request_headers_use_github_token_for_github_api(monkeypatch) -> None:
    module = load_script_module()
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    assert module.request_headers("https://api.github.com/repos/example/project/releases") == {
        "User-Agent": module.USER_AGENT,
        "Authorization": "Bearer test-token",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def test_request_headers_do_not_send_github_token_to_other_hosts(monkeypatch) -> None:
    module = load_script_module()
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    assert module.request_headers("https://registry.npmjs.org/example") == {
        "User-Agent": module.USER_AGENT,
    }


def test_fetch_latest_wallet_gateway_version_paginates_releases(monkeypatch) -> None:
    module = load_script_module()
    requested_urls: list[str] = []

    def fake_fetch_json(url: str, timeout: float) -> list[dict[str, str]]:
        requested_urls.append(url)
        page = parse_qs(urlparse(url).query).get("page", ["1"])[0]
        if page == "1":
            return [{"tag_name": "@canton-network/core-wallet-store@1.7.0"}]
        if page == "2":
            return [{"tag_name": "@canton-network/wallet-gateway-remote@1.4.0"}]
        return []

    monkeypatch.setattr(module, "fetch_json", fake_fetch_json)

    assert module.fetch_latest_wallet_gateway_version(timeout=1.0) == "1.4.0"
    assert requested_urls == [
        f"{module.WALLET_GATEWAY_RELEASES_URL}?per_page=100&page=1",
        f"{module.WALLET_GATEWAY_RELEASES_URL}?per_page=100&page=2",
        f"{module.WALLET_GATEWAY_RELEASES_URL}?per_page=100&page=3",
    ]


def test_parse_dars_lock_selects_latest_dashboard_packages_only() -> None:
    module = load_script_module()
    dars_lock = """
splice-amulet 0.1.17 abc
splice-amulet 0.1.18 def
splice-wallet 0.1.19 abc
splice-dso-governance 0.1.23 abc
splice-dso-governance 0.1.24 def
unrelated-package 9.9.9 abc
"""

    assert module.parse_dars_lock(dars_lock, "test-lock") == {
        "splice-amulet": "0.1.18",
        "splice-wallet": "0.1.19",
        "splice-dso-governance": "0.1.24",
    }
