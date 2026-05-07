from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.harness.characterization_preview import build_characterization_preview_site


class CharacterizationPreviewTests(unittest.TestCase):
    def test_build_preview_site_writes_docs_json_and_expected_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "site"

            written = build_characterization_preview_site(output_root)

            self.assertIn(output_root / "docs.json", written)
            self.assertIn(output_root / "index.mdx", written)

            docs_json = json.loads((output_root / "docs.json").read_text(encoding="utf-8"))
            self.assertEqual(docs_json["name"], "x2mdx Characterization Preview")
            self.assertEqual(docs_json["navigation"]["groups"][0]["group"], "Overview")

            group_names = [group["group"] for group in docs_json["navigation"]["groups"]]
            self.assertEqual(
                group_names,
                [
                    "Overview",
                    "JVM Docs",
                    "DAML JSON",
                    "Protobuf",
                    "TypeDoc",
                    "AsyncAPI",
                    "OpenRPC",
                ],
            )

            self.assertTrue((output_root / "reference" / "jvm-docs-layout" / "ledger-api-jvm-bindings.mdx").exists())
            self.assertTrue((output_root / "appdev" / "reference" / "daml-standard-library" / "index.mdx").exists())
            self.assertTrue((output_root / "reference" / "protobuf-history" / "index.mdx").exists())
            self.assertTrue((output_root / "reference" / "typedoc" / "typescript.mdx").exists())
            self.assertTrue((output_root / "reference" / "asyncapi-single-file" / "json-api-asyncapi-reference.mdx").exists())
            self.assertTrue((output_root / "reference" / "wallet-gateway-json-rpc" / "index.mdx").exists())
            self.assertTrue((output_root / "reference" / "wallet-gateway-json-rpc-alt" / "index.mdx").exists())
            self.assertTrue(
                (
                    output_root
                    / "reference"
                    / "wallet-gateway-json-rpc-alt"
                    / "rpc-specs"
                    / "user-api.mdx"
                ).exists()
            )

            overview = (output_root / "index.mdx").read_text(encoding="utf-8")
            self.assertIn("x2mdx Characterization Preview", overview)
            self.assertIn("Overview and details layout", overview)
            self.assertIn("Docs Nav Snapshot", overview)

            daml_index = (
                output_root / "appdev" / "reference" / "daml-standard-library" / "index.mdx"
            ).read_text(encoding="utf-8")
            self.assertIn("/appdev/reference/daml-standard-library/da-list", daml_index)

            openrpc_default = (
                output_root / "reference" / "wallet-gateway-json-rpc" / "index.mdx"
            ).read_text(encoding="utf-8")
            self.assertIn("/reference/wallet-gateway-json-rpc/specs/user-api", openrpc_default)

            openrpc_alt = (
                output_root / "reference" / "wallet-gateway-json-rpc-alt" / "index.mdx"
            ).read_text(encoding="utf-8")
            self.assertIn("/reference/wallet-gateway-json-rpc-alt/rpc-specs/user-api", openrpc_alt)
            self.assertNotIn("/reference/wallet-gateway-json-rpc/rpc-specs/user-api", openrpc_alt)

            openrpc_alt_spec = (
                output_root / "reference" / "wallet-gateway-json-rpc-alt" / "rpc-specs" / "user-api.mdx"
            ).read_text(encoding="utf-8")
            self.assertIn('href="/reference/wallet-gateway-json-rpc-alt/wallet-gateway-overview"', openrpc_alt_spec)


if __name__ == "__main__":
    unittest.main()
