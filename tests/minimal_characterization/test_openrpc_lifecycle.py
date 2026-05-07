from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.minimal_characterization.helpers import (
    assert_contains_all,
    assert_contains_none,
    assert_text_tree_matches_fixture,
    mdx_file_set,
    read_mdx,
    run_x2mdx,
)


class OpenRpcMinimalLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_json(self, relative_path: str, payload: object) -> Path:
        path = self.root / "fixtures" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def _write_manifest(self) -> Path:
        wallet_v1 = {
            "openrpc": "1.2.6",
            "info": {"title": "Wallet API", "version": "1.0.0"},
            "methods": [
                {
                    "name": "listPayments",
                    "description": "Legacy payment listing.",
                    "params": [],
                    "result": {"name": "result", "schema": {"$ref": "wallet.json#/components/schemas/PaymentResult"}},
                }
            ],
            "components": {
                "schemas": {
                    "PaymentResult": {
                        "type": "object",
                        "required": ["paymentId"],
                        "properties": {"paymentId": {"type": "string"}},
                    }
                }
            },
        }
        wallet_v2 = {
            "openrpc": "1.2.6",
            "info": {"title": "Wallet API", "version": "1.1.0"},
            "methods": [
                {
                    "name": "alphaPayments",
                    "x-state": "alpha",
                    "description": "Experimental payment listing.",
                    "params": [],
                    "result": {"name": "result", "schema": {"$ref": "wallet.json#/components/schemas/PaymentResult"}},
                },
                {
                    "name": "previewPayments",
                    "x-state": "beta",
                    "description": "Preview payment listing.",
                    "params": [],
                    "result": {"name": "result", "schema": {"type": "string"}},
                },
                {
                    "name": "listPaymentsV2",
                    "x-state": "stable",
                    "x-replaces": "listPayments",
                    "description": "Stable payment listing.",
                    "params": [
                        {
                            "name": "request",
                            "schema": {
                                "type": "object",
                                "required": ["party"],
                                "properties": {"party": {"type": "string"}},
                            },
                        }
                    ],
                    "result": {"name": "result", "schema": {"$ref": "wallet.json#/components/schemas/PaymentResult"}},
                },
                {
                    "name": "listLegacyPayments",
                    "x-state": "deprecated",
                    "description": "Deprecated payment listing.",
                    "params": [],
                    "result": {"name": "result", "schema": {"type": "string"}},
                },
            ],
            "components": {
                "schemas": {
                    "PaymentResult": {
                        "type": "object",
                        "required": ["paymentId", "amount"],
                        "properties": {"paymentId": {"type": "string"}, "amount": {"type": "number"}},
                    }
                }
            },
        }
        remote_v1 = {
            "openrpc": "1.2.6",
            "info": {"title": "Remote API", "version": "1.0.0"},
            "methods": [
                {
                    "name": "status",
                    "description": "Return remote status.",
                    "params": [],
                    "result": {"name": "result", "schema": {"type": "string"}},
                }
            ],
            "components": {"schemas": {}},
        }
        remote_v2 = {
            "openrpc": "1.2.6",
            "info": {"title": "Remote API", "version": "1.1.0"},
            "methods": [
                {
                    "name": "status",
                    "description": "Return remote status.",
                    "params": [],
                    "result": {"name": "result", "schema": {"$ref": "wallet.json#/components/schemas/PaymentResult"}},
                }
            ],
            "components": {"schemas": {}},
        }

        self._write_json("1.0.0/wallet.json", wallet_v1)
        self._write_json("1.1.0/wallet.json", wallet_v2)
        self._write_json("1.0.0/remote.json", remote_v1)
        self._write_json("1.1.0/remote.json", remote_v2)
        return self._write_json(
            "manifest.json",
            {
                "source": "minimal openrpc lifecycle fixtures",
                "publish_version": "1.1.0",
                "specs": [
                    {
                        "spec_id": "wallet",
                        "display_name": "Wallet API",
                        "source_path": "wallet.json",
                        "versions": [
                            {"version": "1.0.0", "fixture_path": "1.0.0/wallet.json", "source_path": "wallet.json"},
                            {"version": "1.1.0", "fixture_path": "1.1.0/wallet.json", "source_path": "wallet.json"},
                        ],
                    },
                    {
                        "spec_id": "remote",
                        "display_name": "Remote API",
                        "source_path": "remote.json",
                        "versions": [
                            {"version": "1.0.0", "fixture_path": "1.0.0/remote.json", "source_path": "remote.json"},
                            {"version": "1.1.0", "fixture_path": "1.1.0/remote.json", "source_path": "remote.json"},
                        ],
                    },
                ],
            },
        )

    def _render_pages(self, relative_output_dir: str = "openrpc") -> Path:
        manifest_path = self._write_manifest()
        output_dir = self.root / "out" / relative_output_dir
        run_x2mdx(
            [
                "openrpc",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(output_dir),
                "--publish-version",
                "1.1.0",
                "--source-name",
                "minimal openrpc lifecycle fixtures",
                "--version-filter",
                "minimal versions",
                "--overview-name",
                "wallet-gateway-overview.mdx",
                "--spec-dir-name",
                "rpc-specs",
                "--link-prefix",
                "/reference/wallet-gateway-json-rpc",
            ]
        )
        return output_dir

    def test_cli_renders_minimal_source_contract(self) -> None:
        output_dir = self._render_pages()

        self.assertEqual(
            mdx_file_set(output_dir),
            {
                "wallet-gateway-overview.mdx",
                "rpc-specs/remote.mdx",
                "rpc-specs/wallet.mdx",
                "operations/remote/status.mdx",
                "operations/wallet/alphapayments.mdx",
                "operations/wallet/listlegacypayments.mdx",
                "operations/wallet/listpayments.mdx",
                "operations/wallet/listpaymentsv2.mdx",
                "operations/wallet/previewpayments.mdx",
            },
        )
        assert_text_tree_matches_fixture(output_dir, "openrpc/default")

        overview = read_mdx(output_dir, "wallet-gateway-overview.mdx")
        remote_method = read_mdx(output_dir, "operations/remote/status.mdx")
        assert_contains_all(overview, ["/reference/wallet-gateway-json-rpc/rpc-specs/wallet", "Wallet API"])
        assert_contains_all(remote_method, ["PaymentResult", "amount", "x2mdx-ref-schema"])

    def test_cli_renders_explicit_lifecycle_states(self) -> None:
        output_dir = self._render_pages("openrpc-lifecycle")

        assert_text_tree_matches_fixture(output_dir, "openrpc/default")
        wallet_spec = read_mdx(output_dir, "rpc-specs/wallet.mdx")
        stable_method = read_mdx(output_dir, "operations/wallet/listpaymentsv2.mdx")
        deprecated_method = read_mdx(output_dir, "operations/wallet/listlegacypayments.mdx")
        assert_contains_all(wallet_spec, ["Alpha", "Beta", "Stable", "Deprecated"])
        assert_contains_all(stable_method, ["Lifecycle", "Stable"])
        assert_contains_all(deprecated_method, ["Lifecycle", "Deprecated"])

    def test_cli_renders_replacement_metadata(self) -> None:
        output_dir = self._render_pages("openrpc-replacements")

        assert_text_tree_matches_fixture(output_dir, "openrpc/default")
        stable_method = read_mdx(output_dir, "operations/wallet/listpaymentsv2.mdx")
        assert_contains_all(stable_method, ["Replaces", "listPayments", "JSON-RPC listPaymentsV2"])
        assert_contains_none(stable_method, ["x-state", "x-replaces", "## Examples"])

    def test_cli_prunes_stale_output(self) -> None:
        manifest_path = self._write_manifest()
        output_dir = self.root / "out" / "openrpc-prune"
        stale_file = output_dir / "operations" / "stale" / "index.mdx"
        stale_file.parent.mkdir(parents=True, exist_ok=True)
        stale_file.write_text("stale\n", encoding="utf-8")

        run_x2mdx(
            [
                "openrpc",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(output_dir),
                "--publish-version",
                "1.1.0",
                "--source-name",
                "minimal openrpc lifecycle fixtures",
                "--version-filter",
                "minimal versions",
            ]
        )

        self.assertFalse(stale_file.exists())
        assert_text_tree_matches_fixture(output_dir, "openrpc/prune")

    @unittest.skip("openrpc CLI does not expose docs-json navigation flags")
    def test_cli_updates_docs_json_navigation_idempotently(self) -> None:
        pass
