from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_mdx(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'---\ntitle: "{title}"\n---\n', encoding="utf-8")


def test_openrpc_nav_uses_wallet_gateway_section_shape(tmp_path: Path) -> None:
    generate_wallet_gateway_openrpc_reference = load_script("generate_wallet_gateway_openrpc_reference")
    docs_json = tmp_path / "docs-main" / "docs.json"
    docs_json.parent.mkdir(parents=True)
    docs_json.write_text(
        json.dumps(
            {
                "navigation": {
                    "dropdowns": [
                        {
                            "dropdown": "API Reference",
                            "pages": [
                                {"group": "TypeScript", "pages": []},
                                {"group": "Wallet Kernel SDK", "pages": ["old-wallet"]},
                                {"group": "Splice APIs", "pages": []},
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    output_dir = docs_json.parent / "reference" / "wallet-gateway-json-rpc"

    write_mdx(output_dir / "index.mdx", "Wallet Gateway")
    write_mdx(output_dir / "specs" / "dapp-api.mdx", "Sync dApp API")
    write_mdx(output_dir / "specs" / "dapp-remote-api.mdx", "Async dApp API")
    write_mdx(output_dir / "specs" / "user-api.mdx", "User API")
    write_mdx(output_dir / "specs" / "signing-api.mdx", "Signing API")
    write_mdx(output_dir / "operations" / "dapp-api" / "connect.mdx", "connect")
    write_mdx(output_dir / "operations" / "dapp-api" / "details.mdx", "Details and history")
    write_mdx(output_dir / "operations" / "dapp-remote-api" / "connect.mdx", "connect")
    write_mdx(output_dir / "operations" / "dapp-remote-api" / "details.mdx", "Details and history")
    write_mdx(output_dir / "operations" / "user-api" / "createWallet.mdx", "createWallet")
    write_mdx(output_dir / "operations" / "user-api" / "details.mdx", "Details and history")
    write_mdx(output_dir / "operations" / "signing-api" / "signTransaction.mdx", "signTransaction")
    write_mdx(output_dir / "operations" / "signing-api" / "details.mdx", "Details and history")
    write_mdx(output_dir / "operations" / "details.mdx", "Details and history")

    generate_wallet_gateway_openrpc_reference.update_docs_navigation(
        docs_json_path=docs_json,
        dropdown_label="API Reference",
        output_dir=output_dir,
        spec_entries=[
            {"spec_id": "dapp-api"},
            {"spec_id": "dapp-remote-api"},
            {"spec_id": "user-api"},
            {"spec_id": "signing-api"},
        ],
    )
    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    pages = docs["navigation"]["dropdowns"][0]["pages"]

    assert pages == [
        {"group": "TypeScript", "pages": []},
        {
            "group": "dApp API",
            "pages": [
                {
                    "group": "Sync dApp API",
                    "pages": [
                        "reference/wallet-gateway-json-rpc/operations/dapp-api/connect",
                        "reference/wallet-gateway-json-rpc/operations/dapp-api/details",
                    ],
                },
                {
                    "group": "Async dApp API",
                    "pages": [
                        "reference/wallet-gateway-json-rpc/operations/dapp-remote-api/connect",
                        "reference/wallet-gateway-json-rpc/operations/dapp-remote-api/details",
                    ],
                },
            ],
        },
        {
            "group": "Wallet Gateway",
            "pages": [
                {
                    "group": "User API",
                    "pages": [
                        "reference/wallet-gateway-json-rpc/operations/user-api/createWallet",
                        "reference/wallet-gateway-json-rpc/operations/user-api/details",
                    ],
                },
                {
                    "group": "Signing API",
                    "pages": [
                        "reference/wallet-gateway-json-rpc/operations/signing-api/signTransaction",
                        "reference/wallet-gateway-json-rpc/operations/signing-api/details",
                    ],
                },
                "reference/wallet-gateway-json-rpc/operations/details",
            ],
        },
        {"group": "Splice APIs", "pages": []},
    ]


def test_openrpc_nav_updates_api_reference_product_shape(tmp_path: Path) -> None:
    generate_wallet_gateway_openrpc_reference = load_script("generate_wallet_gateway_openrpc_reference")
    docs_json = tmp_path / "docs-main" / "docs.json"
    docs_json.parent.mkdir(parents=True)
    docs_json.write_text(
        json.dumps(
            {
                "navigation": {
                    "products": [
                        {"product": "Overview", "groups": []},
                        {
                            "product": "API Reference",
                            "pages": [
                                {"group": "TypeScript", "pages": []},
                                {"group": "Wallet Gateway JSON-RPC", "pages": ["old-wallet"]},
                            ],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    output_dir = docs_json.parent / "reference" / "wallet-gateway-json-rpc"

    write_mdx(output_dir / "index.mdx", "Wallet Gateway")
    write_mdx(output_dir / "specs" / "user-api.mdx", "User API")
    write_mdx(output_dir / "operations" / "user-api" / "createWallet.mdx", "createWallet")
    write_mdx(output_dir / "operations" / "user-api" / "details.mdx", "User API details and history")
    write_mdx(output_dir / "operations" / "details.mdx", "Details and history")

    generate_wallet_gateway_openrpc_reference.update_docs_navigation(
        docs_json_path=docs_json,
        dropdown_label="API Reference",
        output_dir=output_dir,
        spec_entries=[{"spec_id": "user-api"}],
    )
    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    pages = docs["navigation"]["products"][1]["pages"]

    assert pages == [
        {"group": "TypeScript", "pages": []},
        {
            "group": "Wallet Gateway",
            "pages": [
                {
                    "group": "User API",
                    "pages": [
                        "reference/wallet-gateway-json-rpc/operations/user-api/createWallet",
                        "reference/wallet-gateway-json-rpc/operations/user-api/details",
                    ],
                },
                "reference/wallet-gateway-json-rpc/operations/details",
            ],
        },
    ]


def test_openrpc_nav_group_helper_omits_redundant_spec_page_child(tmp_path: Path) -> None:
    generated_reference_nav = load_script("generated_reference_nav")
    docs_json = tmp_path / "docs-main" / "docs.json"
    docs_json.parent.mkdir(parents=True)
    docs_json.write_text("{}", encoding="utf-8")
    output_dir = docs_json.parent / "reference" / "wallet-gateway-json-rpc"

    write_mdx(output_dir / "specs" / "dapp-api.mdx", "Sync dApp API")
    write_mdx(output_dir / "operations" / "dapp-api" / "connect.mdx", "connect")

    group = generated_reference_nav.build_openrpc_nav_group(
        output_dir=output_dir,
        docs_json_path=docs_json,
        group_label="dApp API",
        spec_ids=["dapp-api"],
    )

    assert group == {
        "group": "dApp API",
        "pages": [
            {
                "group": "Sync dApp API",
                "pages": [
                    "reference/wallet-gateway-json-rpc/operations/dapp-api/connect",
                ],
            },
        ],
    }


def test_aggregate_generation_rejects_duplicate_wallet_gateway_aliases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generate_all_reference_docs = load_script("generate_all_reference_docs")
    docs_json = tmp_path / "docs-main" / "docs.json"
    docs_json.parent.mkdir(parents=True)
    docs_json.write_text(
        json.dumps(
            {
                "navigation": {
                    "dropdowns": [
                        {
                            "dropdown": "API Reference",
                            "pages": [
                                {"group": "Wallet Gateway", "pages": []},
                                {"group": "Wallet Kernel SDK", "pages": []},
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(generate_all_reference_docs, "DOCS_JSON_PATH", docs_json)

    with pytest.raises(ValueError, match="Duplicate Wallet Gateway navigation groups"):
        generate_all_reference_docs.assert_no_duplicate_top_group_aliases(
            json.loads(docs_json.read_text(encoding="utf-8"))
        )


def test_aggregate_generation_replaces_legacy_wallet_kernel_group() -> None:
    generate_all_reference_docs = load_script("generate_all_reference_docs")
    pages = [
        {"group": "TypeScript", "pages": []},
        {"group": "Wallet Kernel", "pages": ["old"]},
        {"group": "Wallet Gateway JSON-RPC", "pages": ["old-alias"]},
        {"group": "Splice APIs", "pages": []},
    ]

    generate_all_reference_docs.replace_group(
        pages,
        {"group": "Wallet Gateway", "pages": ["new"]},
        aliases=generate_all_reference_docs.top_group_aliases("Wallet Gateway"),
    )

    assert pages == [
        {"group": "TypeScript", "pages": []},
        {"group": "Wallet Gateway", "pages": ["new"]},
        {"group": "Splice APIs", "pages": []},
    ]
