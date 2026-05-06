from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.minimal_characterization.helpers import (
    assert_contains_all,
    assert_contains_none,
    assert_text_file_matches_fixture,
    assert_text_tree_matches_fixture,
    mdx_file_set,
    read_mdx,
    run_x2mdx,
)


def write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(contents).lstrip(), encoding="utf-8")


class AsyncApiMinimalLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_manifest(self) -> Path:
        fixture_root = self.root / "fixtures"
        write_text(
            fixture_root / "1.0.0" / "asyncapi.yaml",
            """
            asyncapi: 2.6.0
            info:
              title: Minimal Lifecycle WebSocket API
              version: 1.0.0
            channels:
              payments.created:
                description: Legacy payment creation stream.
                subscribe:
                  operationId: onPaymentsCreated
                  message:
                    $ref: '#/components/messages/PaymentEvent'
            components:
              messages:
                PaymentEvent:
                  contentType: application/json
                  payload:
                    $ref: '#/components/schemas/PaymentEvent'
              schemas:
                PaymentEvent:
                  type: object
                  required: [paymentId]
                  properties:
                    paymentId:
                      type: string
            """,
        )
        write_text(
            fixture_root / "1.1.0" / "asyncapi.yaml",
            """
            asyncapi: 2.6.0
            info:
              title: Minimal Lifecycle WebSocket API
              version: 1.1.0
            channels:
              payments.alpha:
                x-state: alpha
                description: Experimental payment stream.
                subscribe:
                  operationId: onAlphaPayments
                  message:
                    $ref: '#/components/messages/PaymentEvent'
              payments.preview:
                x-state: beta
                description: Preview payment stream.
                subscribe:
                  operationId: onPreviewPayments
                  message:
                    $ref: '#/components/messages/PaymentEvent'
              payments.created.v2:
                x-state: stable
                x-replaces: payments.created
                description: Stable payment creation stream.
                subscribe:
                  operationId: onPaymentsCreatedV2
                  message:
                    $ref: '#/components/messages/PaymentEventV2'
              payments.legacy:
                x-state: deprecated
                description: Deprecated payment stream.
                subscribe:
                  operationId: onLegacyPayments
                  message:
                    $ref: '#/components/messages/PaymentEvent'
            components:
              messages:
                PaymentEvent:
                  contentType: application/json
                  payload:
                    $ref: '#/components/schemas/PaymentEvent'
                PaymentEventV2:
                  contentType: application/json
                  payload:
                    $ref: '#/components/schemas/PaymentEventV2'
              schemas:
                PaymentEvent:
                  type: object
                  required: [paymentId]
                  properties:
                    paymentId:
                      type: string
                PaymentEventV2:
                  type: object
                  required: [paymentId, amount]
                  properties:
                    paymentId:
                      type: string
                    amount:
                      type: number
            """,
        )
        manifest_path = fixture_root / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "source": "minimal asyncapi lifecycle fixtures",
                    "versions": [
                        {
                            "version": "1.0.0",
                            "source_path": "published/1.0.0/asyncapi.yaml",
                            "fixture_path": "1.0.0/asyncapi.yaml",
                        },
                        {
                            "version": "1.1.0",
                            "source_path": "published/1.1.0/asyncapi.yaml",
                            "fixture_path": "1.1.0/asyncapi.yaml",
                        },
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return manifest_path

    def _render_pages(self, relative_output_dir: str = "asyncapi") -> Path:
        manifest_path = self._write_manifest()
        output_dir = self.root / "out" / relative_output_dir
        run_x2mdx(
            [
                "asyncapi",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(output_dir),
                "--publish-version",
                "1.1.0",
                "--source-name",
                "minimal asyncapi lifecycle fixtures",
                "--version-filter",
                "minimal versions",
            ]
        )
        return output_dir

    def test_cli_renders_minimal_source_contract(self) -> None:
        output_dir = self._render_pages()

        self.assertEqual(
            mdx_file_set(output_dir),
            {
                "index.mdx",
                "channels/payments-alpha.mdx",
                "channels/payments-created-v2.mdx",
                "channels/payments-legacy.mdx",
                "channels/payments-preview.mdx",
                "channels/payments-created.mdx",
                "operations/payments-alpha/subscribe.mdx",
                "operations/payments-created-v2/subscribe.mdx",
                "operations/payments-legacy/subscribe.mdx",
                "operations/payments-preview/subscribe.mdx",
                "operations/payments-created/subscribe.mdx",
            },
        )
        assert_text_tree_matches_fixture(output_dir, "asyncapi/default")

        overview = read_mdx(output_dir, "index.mdx")
        alpha_operation = read_mdx(output_dir, "operations/payments-alpha/subscribe.mdx")
        assert_contains_all(overview, ["minimal asyncapi lifecycle fixtures", "minimal versions", "payments.created"])
        assert_contains_all(alpha_operation, ["WebSocket", "SUBSCRIBE", "JSON API AsyncAPI"])

    def test_cli_renders_explicit_lifecycle_states(self) -> None:
        output_dir = self._render_pages("asyncapi-lifecycle")

        assert_text_tree_matches_fixture(output_dir, "asyncapi/default")
        overview = read_mdx(output_dir, "index.mdx")
        alpha_operation = read_mdx(output_dir, "operations/payments-alpha/subscribe.mdx")
        deprecated_operation = read_mdx(output_dir, "operations/payments-legacy/subscribe.mdx")
        assert_contains_all(overview, ["Alpha", "Beta", "Stable", "Deprecated"])
        assert_contains_all(alpha_operation, ["Lifecycle", "Alpha"])
        assert_contains_all(deprecated_operation, ["Lifecycle", "Deprecated"])

    def test_cli_renders_replacement_metadata(self) -> None:
        output_dir = self._render_pages("asyncapi-replacements")

        assert_text_tree_matches_fixture(output_dir, "asyncapi/default")
        stable_channel = read_mdx(output_dir, "channels/payments-created-v2.mdx")
        assert_contains_all(stable_channel, ["Lifecycle", "Stable", "Replaces", "payments.created"])
        assert_contains_none(stable_channel, ["x-state", "x-replaces"])

    def test_cli_prunes_stale_output(self) -> None:
        manifest_path = self._write_manifest()
        output_dir = self.root / "out" / "asyncapi-prune"
        stale_file = output_dir / "channels" / "stale.mdx"
        stale_file.parent.mkdir(parents=True, exist_ok=True)
        stale_file.write_text("stale\n", encoding="utf-8")

        run_x2mdx(
            [
                "asyncapi",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(output_dir),
                "--publish-version",
                "1.1.0",
                "--source-name",
                "minimal asyncapi lifecycle fixtures",
                "--version-filter",
                "minimal versions",
            ]
        )

        self.assertFalse(stale_file.exists())
        assert_text_tree_matches_fixture(output_dir, "asyncapi/default")

    def test_cli_updates_docs_json_navigation_idempotently(self) -> None:
        manifest_path = self._write_manifest()
        docs_root = self.root / "docs"
        output_dir = docs_root / "reference" / "json-api-asyncapi"
        docs_json = docs_root / "docs.json"
        docs_json.parent.mkdir(parents=True, exist_ok=True)
        docs_json.write_text(
            json.dumps(
                {
                    "navigation": {
                        "dropdowns": [
                            {
                                "dropdown": "API Reference",
                                "versions": [
                                    {"version": "DevNet", "pages": []},
                                    {"version": "MainNet", "pages": []},
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

        args = [
            "asyncapi",
            "build-api-pages-from-manifest",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--overview-name",
            "index.mdx",
            "--docs-json",
            str(docs_json),
            "--nav-dropdown",
            "API Reference",
            "--nav-version",
            "DevNet",
            "--nav-group",
            "Ledger API Endpoints",
            "--nav-group",
            "WebSocket APIs",
        ]
        run_x2mdx(args)
        run_x2mdx(args)

        assert_text_file_matches_fixture(docs_json, "asyncapi/docs-json/docs.json")
        docs = json.loads(docs_json.read_text(encoding="utf-8"))
        versions = docs["navigation"]["dropdowns"][0]["versions"]
        self.assertEqual(
            versions[0]["groups"],
            [
                {
                    "group": "Ledger API Endpoints",
                    "pages": [],
                    "groups": [
                        {
                            "group": "WebSocket APIs",
                            "pages": ["reference/json-api-asyncapi/index"],
                        }
                    ],
                }
            ],
        )
        self.assertEqual(versions[1]["pages"], [])
        self.assertEqual(json.dumps(docs).count("reference/json-api-asyncapi/index"), 1)
