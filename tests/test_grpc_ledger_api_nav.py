from __future__ import annotations

import importlib.util
import json
import os
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
    previous = os.environ.get("DIGITAL_ASSET_DOCS_DIRENV")
    os.environ["DIGITAL_ASSET_DOCS_DIRENV"] = "1"
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            os.environ.pop("DIGITAL_ASSET_DOCS_DIRENV", None)
        else:
            os.environ["DIGITAL_ASSET_DOCS_DIRENV"] = previous
    return module


def write_mdx(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'---\ntitle: "{title}"\n---\n', encoding="utf-8")


def test_grpc_cli_defaults_to_ledger_api_nav_group(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = load_script("generate_grpc_ledger_api_reference")

    monkeypatch.setattr(sys, "argv", ["generate_grpc_ledger_api_reference.py"])

    assert generator.parse_args().nav_group == ["Ledger API"]


def test_grpc_nav_update_preserves_admin_api_grpc_group(tmp_path: Path) -> None:
    generator = load_script("generate_grpc_ledger_api_reference")
    docs_json = tmp_path / "docs-main" / "docs.json"
    docs_json.parent.mkdir(parents=True)
    docs_json.write_text(
        json.dumps(
            {
                "navigation": {
                    "products": [
                        {
                            "product": "API Reference",
                            "pages": [
                                {"group": "Ledger API", "pages": []},
                                {
                                    "group": "Admin API",
                                    "pages": [
                                        {
                                            "group": "gRPC API",
                                            "pages": [
                                                "reference/admin-api/protobuf/packages/com-digitalasset-canton-admin"
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = docs_json.parent / "reference" / "grpc-ledger-api-reference"
    details_path = output_dir / "details.mdx"
    package_path = output_dir / "com-daml-ledger-api-v2.mdx"
    operation_path = output_dir / "com-daml-ledger-api-v2" / "commandservice" / "submitandwait.mdx"
    write_mdx(details_path, "Details and history")
    write_mdx(package_path, "com.daml.ledger.api.v2")
    write_mdx(operation_path, "SubmitAndWait")

    generator.update_docs_navigation(
        docs_json_path=docs_json,
        dropdown_label="API Reference",
        parent_groups=["Ledger API"],
        insert_after_group=None,
        details_path=details_path,
        page_paths=[package_path, operation_path],
    )

    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    api_pages = docs["navigation"]["products"][0]["pages"]
    ledger = next(item for item in api_pages if item["group"] == "Ledger API")
    admin = next(item for item in api_pages if item["group"] == "Admin API")

    assert next(item for item in ledger["pages"] if item["group"] == "gRPC API")
    assert admin["pages"] == [
        {
            "group": "gRPC API",
            "pages": ["reference/admin-api/protobuf/packages/com-digitalasset-canton-admin"],
        }
    ]
