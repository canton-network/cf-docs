from __future__ import annotations

import json
import importlib.util
import sys
import os
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module():
    os.environ.setdefault("DIGITAL_ASSET_DOCS_DIRENV", "1")
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "generate_grpc_ledger_api_reference",
        REPO_ROOT / "scripts" / "generate_grpc_ledger_api_reference.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_grpc_ledger_api_reference"] = module
    spec.loader.exec_module(module)
    return module


generate_grpc_ledger_api_reference = load_script_module()
DETAILS_LABEL = generate_grpc_ledger_api_reference.DETAILS_LABEL


class GrpcLedgerApiNavTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.docs_json = self.root / "docs-main" / "docs.json"
        self.output_dir = self.root / "docs-main" / "reference" / "grpc-ledger-api-reference"
        self.output_dir.mkdir(parents=True)
        self.docs_json.parent.mkdir(parents=True, exist_ok=True)
        self.docs_json.write_text(json.dumps({"navigation": {"dropdowns": []}}) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_page(self, relative_path: str, title: str, *, service: str | None = None) -> Path:
        path = self.output_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        service_markup = ""
        if service:
            service_markup = f"\n<dt>Service</dt>\n<dd>{service}</dd>\n"
        path.write_text(
            f'---\ntitle: "{title}"\n---\n\n<h1 class="x2mdx-ref-title">{title}</h1>\n{service_markup}',
            encoding="utf-8",
        )
        return path

    def test_nav_flattens_packages_and_services_with_package_details_last(self) -> None:
        details_page = self._write_page("details.mdx", DETAILS_LABEL)
        package_page = self._write_page("com-daml-ledger-api-v2.mdx", "v2")
        operation_page = self._write_page(
            "com-daml-ledger-api-v2/commandservice/submitandwait.mdx",
            "SubmitAndWait",
            service="CommandService",
        )

        nav_group, refs = generate_grpc_ledger_api_reference.build_nav_group(
            docs_json_path=self.docs_json,
            details_path=details_page,
            page_paths=[package_page, operation_page],
        )

        self.assertEqual(nav_group["group"], "gRPC API")
        self.assertEqual(
            nav_group["pages"],
            [
                {
                    "group": "v2",
                    "pages": [
                        {
                            "group": "CommandService",
                            "pages": [
                                "reference/grpc-ledger-api-reference/com-daml-ledger-api-v2/commandservice/submitandwait"
                            ],
                        },
                        "reference/grpc-ledger-api-reference/com-daml-ledger-api-v2",
                    ],
                },
                "reference/grpc-ledger-api-reference/details",
            ],
        )
        self.assertNotIn("Packages", json.dumps(nav_group))
        self.assertNotIn("Services", json.dumps(nav_group))
        self.assertEqual(
            refs,
            {
                "reference/grpc-ledger-api-reference/details",
                "reference/grpc-ledger-api-reference/com-daml-ledger-api-v2",
                "reference/grpc-ledger-api-reference/com-daml-ledger-api-v2/commandservice/submitandwait",
            },
        )

    def test_package_pages_are_retitled_after_nav_labels_are_built(self) -> None:
        package_page = self._write_page("com-daml-ledger-api-v2.mdx", "v2")
        operation_page = self._write_page(
            "com-daml-ledger-api-v2/commandservice/submitandwait.mdx",
            "SubmitAndWait",
            service="CommandService",
        )

        generate_grpc_ledger_api_reference.retitle_package_detail_pages(
            output_dir=self.output_dir,
            page_paths=[package_page, operation_page],
        )

        package_text = package_page.read_text(encoding="utf-8")
        operation_text = operation_page.read_text(encoding="utf-8")
        self.assertIn(f'title: "{DETAILS_LABEL}"', package_text)
        self.assertIn(f'<h1 class="x2mdx-ref-title">{DETAILS_LABEL}</h1>', package_text)
        self.assertIn('title: "SubmitAndWait"', operation_text)

    def test_update_docs_navigation_supports_products_navigation(self) -> None:
        details_page = self._write_page("details.mdx", DETAILS_LABEL)
        package_page = self._write_page("com-daml-ledger-api-v2.mdx", "v2")
        operation_page = self._write_page(
            "com-daml-ledger-api-v2/commandservice/submitandwait.mdx",
            "SubmitAndWait",
            service="CommandService",
        )
        self.docs_json.write_text(
            json.dumps(
                {
                    "navigation": {
                        "products": [
                            {
                                "product": "API Reference",
                                "pages": [
                                    "api-reference",
                                    {
                                        "group": "Ledger API",
                                        "pages": [
                                            "appdev/reference/pqs-sql-reference",
                                            {
                                                "group": "gRPC API",
                                                "pages": [
                                                    {
                                                        "group": "Packages",
                                                        "pages": [
                                                            {
                                                                "group": "v2",
                                                                "pages": [
                                                                    "reference/grpc-ledger-api-reference/com-daml-ledger-api-v2",
                                                                    {
                                                                        "group": "Services",
                                                                        "pages": [
                                                                            {
                                                                                "group": "CommandService",
                                                                                "pages": [
                                                                                    "reference/grpc-ledger-api-reference/com-daml-ledger-api-v2/commandservice/submitandwait"
                                                                                ],
                                                                            }
                                                                        ],
                                                                    },
                                                                ],
                                                            }
                                                        ],
                                                    },
                                                    "reference/grpc-ledger-api-reference/details",
                                                ],
                                            },
                                        ],
                                    },
                                    {
                                        "group": "Admin API",
                                        "pages": [
                                            {
                                                "group": "gRPC API",
                                                "pages": [
                                                    {
                                                        "group": "Packages",
                                                        "pages": [
                                                            "reference/admin-api/protobuf/packages/com-digitalasset-canton-admin"
                                                        ],
                                                    }
                                                ],
                                            }
                                        ],
                                    },
                                ],
                            }
                        ]
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

        generate_grpc_ledger_api_reference.update_docs_navigation(
            docs_json_path=self.docs_json,
            dropdown_label="API Reference",
            parent_groups=[],
            insert_after_group=None,
            details_path=details_page,
            page_paths=[package_page, operation_page],
        )
        generate_grpc_ledger_api_reference.reference_nav.regroup_ledger_api_nav(
            docs_json_path=self.docs_json,
            dropdown_label="API Reference",
        )

        docs = json.loads(self.docs_json.read_text(encoding="utf-8"))
        product_pages = docs["navigation"]["products"][0]["pages"]
        ledger_api = next(item for item in product_pages if isinstance(item, dict) and item.get("group") == "Ledger API")
        grpc_api = next(item for item in ledger_api["pages"] if isinstance(item, dict) and item.get("group") == "gRPC API")
        admin_api = next(item for item in product_pages if isinstance(item, dict) and item.get("group") == "Admin API")
        admin_grpc_api = next(
            item for item in admin_api["pages"] if isinstance(item, dict) and item.get("group") == "gRPC API"
        )
        self.assertEqual(
            grpc_api["pages"],
            [
                {
                    "group": "v2",
                    "pages": [
                        {
                            "group": "CommandService",
                            "pages": [
                                "reference/grpc-ledger-api-reference/com-daml-ledger-api-v2/commandservice/submitandwait"
                            ],
                        },
                        "reference/grpc-ledger-api-reference/com-daml-ledger-api-v2",
                    ],
                },
                "reference/grpc-ledger-api-reference/details",
            ],
        )
        self.assertNotIn("Packages", json.dumps(grpc_api))
        self.assertNotIn("Services", json.dumps(grpc_api))
        self.assertIn("reference/admin-api/protobuf/packages/com-digitalasset-canton-admin", json.dumps(admin_grpc_api))
