from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scripts.generate_typescript_bindings_reference import (
    configured_packages,
    update_docs_navigation,
)


class TypeScriptBindingsReferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(
            output_file=str(self.root / "docs-main" / "reference" / "typescript.mdx"),
            publish_version=None,
            source_name="cli source",
            version=None,
            version_filter="cli versions",
            page_title="@daml/types",
            page_description="TypeScript and JavaScript language bindings for Canton.",
        )

    def test_configured_packages_support_output_entry_point_and_typedoc_args(self) -> None:
        args = self._args()
        config = {
            "typedoc_version": "0.27.9",
            "packages": [
                {
                    "package_name": "@daml/types",
                    "versions": ["3.4.11"],
                    "publish_version": "3.4.11",
                    "entry_point": "index.d.ts",
                    "output_file": str(self.root / "docs-main" / "reference" / "typescript.mdx"),
                    "page_title": "@daml/types",
                },
                {
                    "package_name": "@canton-network/wallet-sdk",
                    "versions": ["1.3.1"],
                    "publish_version": "1.3.1",
                    "entry_point": "dist/index.d.ts",
                    "typedoc_args": ["--skipErrorChecking"],
                    "output_file": str(self.root / "docs-main" / "reference" / "typescript" / "wallet-sdk.mdx"),
                    "page_title": "Wallet SDK",
                    "page_description": "Wallet SDK docs.",
                },
            ],
        }

        packages = configured_packages(config, args)

        self.assertEqual([package.package_name for package in packages], ["@daml/types", "@canton-network/wallet-sdk"])
        self.assertEqual(packages[0].entry_point, "index.d.ts")
        self.assertEqual(packages[0].typedoc_args, [])
        self.assertEqual(packages[0].output_file, (self.root / "docs-main" / "reference" / "typescript.mdx").resolve())
        self.assertEqual(packages[1].entry_point, "dist/index.d.ts")
        self.assertEqual(packages[1].typedoc_args, ["--skipErrorChecking"])
        self.assertEqual(
            packages[1].output_file,
            (self.root / "docs-main" / "reference" / "typescript" / "wallet-sdk.mdx").resolve(),
        )
        self.assertEqual(packages[1].page_title, "Wallet SDK")
        self.assertEqual(packages[1].page_description, "Wallet SDK docs.")

    def test_update_docs_navigation_replaces_typescript_group_idempotently(self) -> None:
        docs_root = self.root / "docs-main"
        docs_root.mkdir(parents=True)
        docs_json = docs_root / "docs.json"
        docs_json.write_text(
            json.dumps(
                {
                    "navigation": {
                        "products": [
                            {
                                "product": "API Reference",
                                "pages": [
                                    {"group": "Ledger API", "pages": ["reference/json-api-reference"]},
                                    {
                                        "group": "Daml TypeScript Bindings",
                                        "pages": ["sdks-tools/language-bindings/typescript"],
                                    },
                                    "reference/typescript",
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
        output_files = [
            docs_root / "reference" / "typescript.mdx",
            docs_root / "reference" / "typescript" / "wallet-sdk.mdx",
            docs_root / "reference" / "typescript" / "dapp-sdk.mdx",
        ]

        for _ in range(2):
            update_docs_navigation(
                docs_json_path=docs_json,
                dropdown_label="API Reference",
                output_files=output_files,
                nav_group="TypeScript",
            )

        docs = json.loads(docs_json.read_text(encoding="utf-8"))
        pages = docs["navigation"]["products"][0]["pages"]
        self.assertEqual(
            pages,
            [
                {"group": "Ledger API", "pages": ["reference/json-api-reference"]},
                {
                    "group": "TypeScript",
                    "pages": [
                        "reference/typescript",
                        "reference/typescript/wallet-sdk",
                        "reference/typescript/dapp-sdk",
                    ],
                },
            ],
        )
