from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "update_generated_reference_sources.py"
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


def write_source_config(path: Path, *, publish_version: str) -> None:
    path.write_text(
        json.dumps(
            {
                "source": "test",
                "release_repo": "digital-asset/decentralized-canton-sync",
                "tag_regex": "^v(?P<version>0\\.[0-9]+\\.[0-9]+)$",
                "min_version": "0.5.10",
                "publish_version": publish_version,
                "asset_template": "{version}_openapi.tar.gz",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_wallet_gateway_source_config(path: Path, *, publish_version: str) -> None:
    path.write_text(
        json.dumps(
            {
                "source": "test",
                "release_repo": "hyperledger-labs/splice-wallet-kernel",
                "remote": "https://github.com/hyperledger-labs/splice-wallet-kernel.git",
                "tag_prefix": "@canton-network/wallet-gateway-remote@",
                "min_version": "0.24.0",
                "publish_version": publish_version,
                "specs": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_typescript_bindings_source_config(
    path: Path,
    *,
    daml_types_version: str = "3.4.11",
    wallet_sdk_version: str = "1.3.1",
    dapp_sdk_version: str = "1.1.0",
) -> None:
    path.write_text(
        json.dumps(
            {
                "typedoc_version": "0.27.9",
                "packages": [
                    {
                        "package_name": "@daml/types",
                        "publish_version": daml_types_version,
                        "versions": ["3.4.11"],
                    },
                    {
                        "package_name": "@canton-network/wallet-sdk",
                        "publish_version": wallet_sdk_version,
                        "versions": ["1.3.1"],
                    },
                    {
                        "package_name": "@canton-network/dapp-sdk",
                        "publish_version": dapp_sdk_version,
                        "versions": ["1.1.0"],
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_ledger_api_source_config(path: Path, *, canton_version: str) -> None:
    path.write_text(
        json.dumps(
            {
                "source": "test",
                "release_url_template": "https://www.canton.io/releases/canton-open-source-{canton_version}.tar.gz",
                "publish_version": "3.5",
                "versions": [
                    {"version": "3.4", "canton_version": "3.4.11"},
                    {"version": "3.5", "canton_version": canton_version},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_ledger_bindings_source_config(path: Path, *, versions: list[str] | None = None) -> None:
    path.write_text(
        json.dumps(
            {
                "repo_base": "https://repo1.maven.org/maven2",
                "artifacts": [
                    {
                        "group": "com.daml",
                        "artifact": "bindings-java",
                        "language": "java",
                        "versions": versions or ["3.4.11"],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_daml_standard_library_source_config(path: Path, *, publish_version: str) -> None:
    path.write_text(
        json.dumps(
            {
                "source": "test",
                "publish_version": publish_version,
                "package_set": "base",
                "sdk_source": "dpm",
                "versions": ["3.4.11"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_update_splice_openapi_source_updates_stale_publish_version(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_source_config(source_config_path, publish_version="0.5.18")
    module.splice_openapi.splice_openapi_generator.selected_releases = lambda **_kwargs: [
        {"version": "0.5.18"},
        {"version": "0.6.7"},
    ]

    update = module.splice_openapi.update_source(
        source_config_path=source_config_path,
        dry_run=False,
    )

    assert update == module.SourceUpdate(
        source="Splice OpenAPI",
        path=source_config_path,
        field="publish_version",
        previous="0.5.18",
        current="0.6.7",
    )
    assert json.loads(source_config_path.read_text(encoding="utf-8"))["publish_version"] == "0.6.7"


def test_update_splice_openapi_source_noops_when_current(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_source_config(source_config_path, publish_version="0.6.7")
    module.splice_openapi.splice_openapi_generator.selected_releases = lambda **_kwargs: [
        {"version": "0.5.18"},
        {"version": "0.6.7"},
    ]

    assert (
        module.splice_openapi.update_source(
            source_config_path=source_config_path,
            dry_run=False,
        )
        is None
    )
    assert json.loads(source_config_path.read_text(encoding="utf-8"))["publish_version"] == "0.6.7"


def test_update_splice_openapi_source_dry_run_does_not_write(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_source_config(source_config_path, publish_version="0.5.18")
    module.splice_openapi.splice_openapi_generator.selected_releases = lambda **_kwargs: [
        {"version": "0.5.18"},
        {"version": "0.6.7"},
    ]

    update = module.splice_openapi.update_source(
        source_config_path=source_config_path,
        dry_run=True,
    )

    assert update is not None
    assert update.previous == "0.5.18"
    assert update.current == "0.6.7"
    assert json.loads(source_config_path.read_text(encoding="utf-8"))["publish_version"] == "0.5.18"


def test_update_wallet_gateway_openrpc_source_updates_stale_publish_version(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_wallet_gateway_source_config(source_config_path, publish_version="0.25.0")
    module.wallet_gateway_openrpc.wallet_gateway_openrpc_generator.stable_release_versions = (
        lambda **_kwargs: [
            "0.25.0",
            "1.4.0",
        ]
    )

    update = module.wallet_gateway_openrpc.update_source(
        source_config_path=source_config_path,
        dry_run=False,
    )

    assert update == module.SourceUpdate(
        source="Wallet Gateway OpenRPC",
        path=source_config_path,
        field="publish_version",
        previous="0.25.0",
        current="1.4.0",
    )
    assert json.loads(source_config_path.read_text(encoding="utf-8"))["publish_version"] == "1.4.0"


def test_update_wallet_gateway_openrpc_source_noops_when_current(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_wallet_gateway_source_config(source_config_path, publish_version="1.4.0")
    module.wallet_gateway_openrpc.wallet_gateway_openrpc_generator.stable_release_versions = (
        lambda **_kwargs: [
            "0.25.0",
            "1.4.0",
        ]
    )

    assert (
        module.wallet_gateway_openrpc.update_source(
            source_config_path=source_config_path,
            dry_run=False,
        )
        is None
    )
    assert json.loads(source_config_path.read_text(encoding="utf-8"))["publish_version"] == "1.4.0"


def test_update_wallet_gateway_openrpc_source_dry_run_does_not_write(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_wallet_gateway_source_config(source_config_path, publish_version="0.25.0")
    module.wallet_gateway_openrpc.wallet_gateway_openrpc_generator.stable_release_versions = (
        lambda **_kwargs: [
            "0.25.0",
            "1.4.0",
        ]
    )

    update = module.wallet_gateway_openrpc.update_source(
        source_config_path=source_config_path,
        dry_run=True,
    )

    assert update is not None
    assert update.previous == "0.25.0"
    assert update.current == "1.4.0"
    assert json.loads(source_config_path.read_text(encoding="utf-8"))["publish_version"] == "0.25.0"


def test_update_typescript_bindings_source_updates_stale_package_versions(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_typescript_bindings_source_config(source_config_path)
    latest_versions = {
        "@daml/types": "3.5.2",
        "@canton-network/wallet-sdk": "1.3.1",
        "@canton-network/dapp-sdk": "1.2.0",
    }
    module.typescript_bindings.latest_npm_version = lambda package_name: latest_versions[package_name]

    updates = module.typescript_bindings.update_source(
        source_config_path=source_config_path,
        dry_run=False,
    )

    assert updates == [
        module.SourceUpdate(
            source="TypeScript bindings @daml/types",
            path=source_config_path,
            field="publish_version",
            previous="3.4.11",
            current="3.5.2",
        ),
        module.SourceUpdate(
            source="TypeScript bindings @canton-network/dapp-sdk",
            path=source_config_path,
            field="publish_version",
            previous="1.1.0",
            current="1.2.0",
        ),
    ]
    packages = json.loads(source_config_path.read_text(encoding="utf-8"))["packages"]
    assert packages[0]["publish_version"] == "3.5.2"
    assert packages[0]["versions"] == ["3.4.11", "3.5.2"]
    assert packages[1]["publish_version"] == "1.3.1"
    assert packages[1]["versions"] == ["1.3.1"]
    assert packages[2]["publish_version"] == "1.2.0"
    assert packages[2]["versions"] == ["1.1.0", "1.2.0"]


def test_update_typescript_bindings_source_noops_when_current(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_typescript_bindings_source_config(
        source_config_path,
        daml_types_version="3.5.2",
        wallet_sdk_version="1.3.1",
        dapp_sdk_version="1.2.0",
    )
    latest_versions = {
        "@daml/types": "3.5.2",
        "@canton-network/wallet-sdk": "1.3.1",
        "@canton-network/dapp-sdk": "1.2.0",
    }
    module.typescript_bindings.latest_npm_version = lambda package_name: latest_versions[package_name]

    assert module.typescript_bindings.update_source(
        source_config_path=source_config_path,
        dry_run=False,
    ) == []


def test_update_typescript_bindings_source_dry_run_does_not_write(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_typescript_bindings_source_config(source_config_path)
    module.typescript_bindings.latest_npm_version = lambda package_name: {
        "@daml/types": "3.5.2",
        "@canton-network/wallet-sdk": "1.3.1",
        "@canton-network/dapp-sdk": "1.2.0",
    }[package_name]

    updates = module.typescript_bindings.update_source(
        source_config_path=source_config_path,
        dry_run=True,
    )

    assert [update.current for update in updates] == ["3.5.2", "1.2.0"]
    packages = json.loads(source_config_path.read_text(encoding="utf-8"))["packages"]
    assert packages[0]["publish_version"] == "3.4.11"
    assert packages[2]["publish_version"] == "1.1.0"


def test_update_ledger_api_source_updates_publish_version_canton_release(tmp_path: Path) -> None:
    module = load_script_module()
    assert module.canton_release_bundles.DEFAULT_CANTON_REMOTE == "https://github.com/digital-asset/canton.git"
    source_config_path = tmp_path / "source-artifacts.json"
    write_ledger_api_source_config(source_config_path, canton_version="3.5.0-snapshot.20260405.18555.0.vbee160e5")
    module.canton_release_bundles.latest_public_canton_bundle_version = lambda *_args, **_kwargs: "3.5.5"

    update = module.canton_release_bundles.update_source(
        source_config_path=source_config_path,
        dry_run=False,
    )

    assert update == module.SourceUpdate(
        source="JSON Ledger API release bundle",
        path=source_config_path,
        field="versions[3.5].canton_version",
        previous="3.5.0-snapshot.20260405.18555.0.vbee160e5",
        current="3.5.5",
    )
    versions = json.loads(source_config_path.read_text(encoding="utf-8"))["versions"]
    assert versions[1]["canton_version"] == "3.5.5"


def test_update_ledger_api_source_noops_when_current(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_ledger_api_source_config(source_config_path, canton_version="3.5.5")
    module.canton_release_bundles.latest_public_canton_bundle_version = lambda *_args, **_kwargs: "3.5.5"

    assert (
        module.canton_release_bundles.update_source(
            source_config_path=source_config_path,
            dry_run=False,
        )
        is None
    )


def test_update_ledger_bindings_source_appends_latest_maven_version(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_ledger_bindings_source_config(source_config_path)
    module.ledger_bindings.latest_maven_version = lambda *_args, **_kwargs: "3.5.5"

    updates = module.ledger_bindings.update_source(
        source_config_path=source_config_path,
        dry_run=False,
    )

    assert updates == [
        module.SourceUpdate(
            source="Java ledger bindings com.daml:bindings-java",
            path=source_config_path,
            field="versions",
            previous="3.4.11",
            current="3.5.5",
        )
    ]
    artifact = json.loads(source_config_path.read_text(encoding="utf-8"))["artifacts"][0]
    assert artifact["versions"] == ["3.4.11", "3.5.5"]


def test_update_ledger_bindings_source_noops_when_latest_is_configured(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_ledger_bindings_source_config(source_config_path, versions=["3.4.11", "3.5.5"])
    module.ledger_bindings.latest_maven_version = lambda *_args, **_kwargs: "3.5.5"

    assert (
        module.ledger_bindings.update_source(
            source_config_path=source_config_path,
            dry_run=False,
        )
        == []
    )


def test_update_daml_standard_library_source_updates_latest_dpm_version(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_daml_standard_library_source_config(source_config_path, publish_version="3.4.11")
    module.daml_standard_library.latest_dpm_version = lambda: "3.5.1"

    update = module.daml_standard_library.update_source(
        source_config_path=source_config_path,
        dry_run=False,
    )

    assert update == module.SourceUpdate(
        source="Daml Standard Library",
        path=source_config_path,
        field="publish_version",
        previous="3.4.11",
        current="3.5.1",
    )
    payload = json.loads(source_config_path.read_text(encoding="utf-8"))
    assert payload["publish_version"] == "3.5.1"
    assert payload["versions"] == ["3.4.11", "3.5.1"]


def test_requested_sources_defaults_to_all_sources() -> None:
    module = load_script_module()

    assert module.requested_sources(type("Args", (), {"sources": None})()) == (
        "splice-openapi",
        "wallet-gateway-openrpc",
        "typescript-bindings",
        "ledger-api",
        "ledger-api-asyncapi",
        "ledger-bindings",
        "daml-standard-library",
    )


def test_requested_sources_preserves_order_and_deduplicates() -> None:
    module = load_script_module()

    assert module.requested_sources(
        type(
            "Args",
            (),
            {
                "sources": [
                    "wallet-gateway-openrpc",
                    "typescript-bindings",
                    "splice-openapi",
                    "wallet-gateway-openrpc",
                ]
            },
        )()
    ) == ("wallet-gateway-openrpc", "typescript-bindings", "splice-openapi")
