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


def test_openrpc_nav_uses_wallet_kernel_details_shape(tmp_path: Path) -> None:
    generated_reference_nav = load_script("generated_reference_nav")
    docs_json = tmp_path / "docs-main" / "docs.json"
    docs_json.parent.mkdir(parents=True)
    docs_json.write_text("{}", encoding="utf-8")
    output_dir = docs_json.parent / "reference" / "wallet-gateway-json-rpc"

    write_mdx(output_dir / "index.mdx", "Wallet Kernel")
    write_mdx(output_dir / "specs" / "dapp-api.mdx", "dApp API")
    write_mdx(output_dir / "operations" / "dapp-api" / "connect.mdx", "connect")
    write_mdx(output_dir / "operations" / "dapp-api" / "details.mdx", "Details and history")
    write_mdx(output_dir / "operations" / "details.mdx", "Details and history")

    group = generated_reference_nav.build_openrpc_nav_group(
        output_dir=output_dir,
        docs_json_path=docs_json,
        group_label="Wallet Kernel",
        spec_ids=["dapp-api"],
    )

    assert group == {
        "group": "Wallet Kernel",
        "pages": [
            {
                "group": "dApp API",
                "pages": [
                    "reference/wallet-gateway-json-rpc/operations/dapp-api/connect",
                    "reference/wallet-gateway-json-rpc/operations/dapp-api/details",
                ],
            },
            "reference/wallet-gateway-json-rpc/operations/details",
        ],
    }


def test_aggregate_generation_rejects_duplicate_wallet_kernel_aliases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
                                {"group": "Wallet Kernel", "pages": []},
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

    with pytest.raises(ValueError, match="Duplicate Wallet Kernel navigation groups"):
        generate_all_reference_docs.assert_no_duplicate_top_group_aliases(
            json.loads(docs_json.read_text(encoding="utf-8"))
        )
