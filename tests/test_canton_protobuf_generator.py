from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts import generate_canton_protobuf_history as generator


class CantonProtobufGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_proto(self, root: Path, relative: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('syntax = "proto3";\n', encoding="utf-8")

    def write_mdx(self, root: Path, relative: str, title: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'---\ntitle: "{title}"\n---\n', encoding="utf-8")

    def test_bundle_selection_maps_only_ledger_and_admin_api_inputs(self) -> None:
        protobuf_root = self.root / "protobuf"
        self.write_proto(protobuf_root / "ledger-api", "com/daml/ledger/api/v2/command_service.proto")
        self.write_proto(protobuf_root / "ledger-api-value", "com/daml/ledger/api/v2/value.proto")
        self.write_proto(protobuf_root / "admin-api", "com/digitalasset/canton/admin/health/v30/status_service.proto")
        self.write_proto(protobuf_root / "community", "com/digitalasset/canton/time/admin/v30/synchronizer_time_service.proto")
        self.write_proto(protobuf_root / "community", "com/digitalasset/canton/crypto/admin/v30/vault_service.proto")
        self.write_proto(protobuf_root / "community", "com/digitalasset/canton/topology/admin/v30/topology_manager_read_service.proto")
        self.write_proto(protobuf_root / "community", "com/digitalasset/canton/protocol/v30/common.proto")
        self.write_proto(protobuf_root / "participant", "com/digitalasset/canton/participant/foo.proto")

        ledger_mapping = generator.import_to_repo_path_from_bundle(
            protobuf_root,
            selections=generator.LEDGER_API_SELECTIONS,
        )
        admin_mapping = generator.import_to_repo_path_from_bundle(
            protobuf_root,
            selections=generator.ADMIN_API_SELECTIONS,
        )

        self.assertEqual(
            ledger_mapping,
            {
                "com/daml/ledger/api/v2/command_service.proto": (
                    "community/ledger-api/src/main/protobuf/com/daml/ledger/api/v2/command_service.proto"
                ),
                "com/daml/ledger/api/v2/value.proto": (
                    "community/daml-lf/ledger-api-value-proto/src/main/protobuf/com/daml/ledger/api/v2/value.proto"
                ),
            },
        )
        self.assertEqual(
            set(admin_mapping),
            {
                "com/digitalasset/canton/admin/health/v30/status_service.proto",
                "com/digitalasset/canton/time/admin/v30/synchronizer_time_service.proto",
                "com/digitalasset/canton/crypto/admin/v30/vault_service.proto",
                "com/digitalasset/canton/topology/admin/v30/topology_manager_read_service.proto",
            },
        )
        self.assertNotIn("com/daml/ledger/api/v2/value.proto", admin_mapping)
        self.assertNotIn("com/digitalasset/canton/protocol/v30/common.proto", admin_mapping)
        self.assertNotIn("com/digitalasset/canton/participant/foo.proto", admin_mapping)

    def test_split_protobuf_navigation_flattens_admin_packages_under_grpc(self) -> None:
        docs_root = self.root / "docs-main"
        docs_json = docs_root / "docs.json"
        docs_root.mkdir(parents=True)
        docs_json.write_text(
            json.dumps(
                {
                    "navigation": {
                        "dropdowns": [
                            {
                                "dropdown": "API Reference",
                                "pages": [
                                    {"group": "Ledger API", "pages": []},
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

        ledger_output = docs_root / "appdev" / "reference" / "protobuf-history"
        ledger_legacy_output = docs_root / "reference" / "protobuf"
        admin_output = docs_root / "reference" / "admin-api" / "protobuf"
        self.write_mdx(ledger_output, "index.mdx", "Details and History")
        self.write_mdx(ledger_legacy_output, "index.mdx", "Details and History")
        self.write_mdx(ledger_legacy_output, "packages/com-daml-ledger-api-v2.mdx", "com.daml.ledger.api.v2")
        self.write_mdx(admin_output, "index.mdx", "Details and History")
        self.write_mdx(admin_output, "packages/com-digitalasset-canton-admin-health-v30.mdx", "com.digitalasset.canton.admin.health.v30")

        generator.update_split_protobuf_navigation(
            docs_json_path=docs_json,
            dropdown_label="API Reference",
            ledger_output_dir=ledger_output,
            ledger_legacy_output_dir=ledger_legacy_output,
            admin_output_dir=admin_output,
        )

        pages = json.loads(docs_json.read_text(encoding="utf-8"))["navigation"]["dropdowns"][0]["pages"]
        ledger = next(item for item in pages if item["group"] == "Ledger API")
        admin = next(item for item in pages if item["group"] == "Admin API")
        ledger_protobuf = next(item for item in ledger["pages"] if item["group"] == "Protobufs")
        admin_grpc = next(item for item in admin["pages"] if item["group"] == "gRPC API")
        admin_packages = next(item for item in admin_grpc["pages"] if isinstance(item, dict) and item["group"] == "Packages")

        self.assertIn("reference/protobuf/index", ledger_protobuf["pages"])
        self.assertEqual(
            admin_packages["pages"],
            [
                {
                    "group": "com.digitalasset.canton.admin.health.v30",
                    "pages": ["reference/admin-api/protobuf/packages/com-digitalasset-canton-admin-health-v30"],
                }
            ],
        )
        self.assertFalse(
            any(isinstance(item, dict) and item.get("group") == "Protobufs" for item in admin_grpc["pages"])
        )
        self.assertEqual(admin_grpc["pages"][-1], "reference/admin-api/protobuf/index")


if __name__ == "__main__":
    unittest.main()
