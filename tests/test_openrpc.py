from __future__ import annotations

import io
import json
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from x2mdx.cli import main as cli_main
from x2mdx.openrpc.lifecycle import build_openrpc_report_from_sources, parse_openrpc
from x2mdx.openrpc.models import OpenRpcSourceSnapshot
from x2mdx.openrpc.render import build_method_page


def write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(contents).lstrip(), encoding="utf-8")


class OpenRpcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _snapshot(self, *, version: str, spec_id: str, display_name: str, source_path: str, contents: str) -> OpenRpcSourceSnapshot:
        return OpenRpcSourceSnapshot(
            version=version,
            spec_id=spec_id,
            display_name=display_name,
            source_path=source_path,
            document=parse_openrpc(textwrap.dedent(contents).lstrip()),
        )

    def _write_manifest(self) -> Path:
        fixture_root = self.root / "fixtures"
        dapp_v1 = """
            {
              "openrpc": "1.2.6",
              "info": {"title": "Dapp API", "version": "1.0.0"},
              "methods": [
                {
                  "name": "status",
                  "description": "Return provider status.",
                  "params": [],
                  "result": {
                    "name": "result",
                    "schema": {"$ref": "api-specs/openrpc-dapp-api.json#/components/schemas/StatusEvent"}
                  }
                }
              ],
              "components": {
                "schemas": {
                  "StatusEvent": {
                    "type": "object",
                    "required": ["connected"],
                    "properties": {
                      "connected": {"type": "boolean"}
                    }
                  }
                }
              }
            }
        """
        dapp_v2 = """
            {
              "openrpc": "1.2.6",
              "info": {"title": "Dapp API", "version": "1.1.0"},
              "methods": [
                {
                  "name": "status",
                  "description": "Return wallet provider status.",
                  "params": [],
                  "result": {
                    "name": "result",
                    "schema": {"$ref": "api-specs/openrpc-dapp-api.json#/components/schemas/StatusEvent"}
                  }
                },
                {
                  "name": "connect",
                  "description": "Connect to a provider.",
                  "params": [],
                  "result": {
                    "name": "result",
                    "schema": {"type": "string"}
                  }
                }
              ],
              "components": {
                "schemas": {
                  "StatusEvent": {
                    "type": "object",
                    "required": ["connected", "network"],
                    "properties": {
                      "connected": {"type": "boolean"},
                      "network": {"type": "string"}
                    }
                  }
                }
              }
            }
        """
        remote_v1 = """
            {
              "openrpc": "1.2.6",
              "info": {"title": "Remote dApp API", "version": "1.0.0"},
              "methods": [
                {
                  "name": "status",
                  "description": "Return remote status.",
                  "params": [],
                  "result": {
                    "name": "result",
                    "schema": {"$ref": "api-specs/openrpc-dapp-api.json#/components/schemas/StatusEvent"}
                  }
                }
              ],
              "components": {"schemas": {}}
            }
        """
        remote_v2 = """
            {
              "openrpc": "1.2.6",
              "info": {"title": "Remote dApp API", "version": "1.1.0"},
              "methods": [
                {
                  "name": "status",
                  "description": "Return remote status.",
                  "params": [],
                  "result": {
                    "name": "result",
                    "schema": {"$ref": "api-specs/openrpc-dapp-api.json#/components/schemas/StatusEvent"}
                  }
                },
                {
                  "name": "prepareExecute",
                  "description": "Prepare a transaction.",
                  "params": [
                    {
                      "name": "params",
                      "schema": {
                        "type": "object",
                        "required": ["txId"],
                        "properties": {
                          "txId": {"type": "string"}
                        }
                      }
                    }
                  ],
                  "result": {
                    "name": "result",
                    "schema": {"type": "string"}
                  }
                }
              ],
              "components": {"schemas": {}}
            }
        """

        versions = {
            "1.0.0": {
                "dapp-api": ("Dapp API", "api-specs/openrpc-dapp-api.json", dapp_v1),
                "remote-dapp-api": ("Remote dApp API", "api-specs/openrpc-dapp-remote-api.json", remote_v1),
            },
            "1.1.0": {
                "dapp-api": ("Dapp API", "api-specs/openrpc-dapp-api.json", dapp_v2),
                "remote-dapp-api": ("Remote dApp API", "api-specs/openrpc-dapp-remote-api.json", remote_v2),
            },
        }

        manifest = {
            "source": "openrpc test fixtures",
            "publish_version": "1.1.0",
            "specs": [],
        }

        for spec_id, display_name, source_path in [
            ("dapp-api", "Dapp API", "api-specs/openrpc-dapp-api.json"),
            ("remote-dapp-api", "Remote dApp API", "api-specs/openrpc-dapp-remote-api.json"),
        ]:
            spec_entry = {
                "spec_id": spec_id,
                "display_name": display_name,
                "source_path": source_path,
                "versions": [],
            }
            for version in ["1.0.0", "1.1.0"]:
                _display_name, _source_path, contents = versions[version][spec_id]
                relative_path = Path(version) / f"{spec_id}.json"
                write_text(fixture_root / relative_path, contents)
                spec_entry["versions"].append(
                    {
                        "version": version,
                        "fixture_path": relative_path.as_posix(),
                    }
                )
            manifest["specs"].append(spec_entry)

        manifest_path = fixture_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest_path

    def test_build_report_tracks_method_changes_across_specs_and_versions(self) -> None:
        report = build_openrpc_report_from_sources(
            [
                self._snapshot(
                    version="1.0.0",
                    spec_id="dapp-api",
                    display_name="Dapp API",
                    source_path="api-specs/openrpc-dapp-api.json",
                    contents="""
                        {
                          "openrpc": "1.2.6",
                          "info": {"title": "Dapp API", "version": "1.0.0"},
                          "methods": [
                            {
                              "name": "status",
                              "description": "Return provider status.",
                              "params": [],
                              "result": {
                                "name": "result",
                                "schema": {"$ref": "api-specs/openrpc-dapp-api.json#/components/schemas/StatusEvent"}
                              }
                            }
                          ],
                          "components": {
                            "schemas": {
                              "StatusEvent": {
                                "type": "object",
                                "required": ["connected"],
                                "properties": {"connected": {"type": "boolean"}}
                              }
                            }
                          }
                        }
                    """,
                ),
                self._snapshot(
                    version="1.0.0",
                    spec_id="remote-dapp-api",
                    display_name="Remote dApp API",
                    source_path="api-specs/openrpc-dapp-remote-api.json",
                    contents="""
                        {
                          "openrpc": "1.2.6",
                          "info": {"title": "Remote dApp API", "version": "1.0.0"},
                          "methods": [
                            {
                              "name": "status",
                              "description": "Return remote status.",
                              "params": [],
                              "result": {
                                "name": "result",
                                "schema": {"$ref": "api-specs/openrpc-dapp-api.json#/components/schemas/StatusEvent"}
                              }
                            }
                          ],
                          "components": {"schemas": {}}
                        }
                    """,
                ),
                self._snapshot(
                    version="1.1.0",
                    spec_id="dapp-api",
                    display_name="Dapp API",
                    source_path="api-specs/openrpc-dapp-api.json",
                    contents="""
                        {
                          "openrpc": "1.2.6",
                          "info": {"title": "Dapp API", "version": "1.1.0"},
                          "methods": [
                            {
                              "name": "status",
                              "description": "Return wallet provider status.",
                              "params": [],
                              "result": {
                                "name": "result",
                                "schema": {"$ref": "api-specs/openrpc-dapp-api.json#/components/schemas/StatusEvent"}
                              }
                            },
                            {
                              "name": "connect",
                              "description": "Connect to a provider.",
                              "params": [],
                              "result": {"name": "result", "schema": {"type": "string"}}
                            }
                          ],
                          "components": {
                            "schemas": {
                              "StatusEvent": {
                                "type": "object",
                                "required": ["connected", "network"],
                                "properties": {
                                  "connected": {"type": "boolean"},
                                  "network": {"type": "string"}
                                }
                              }
                            }
                          }
                        }
                    """,
                ),
                self._snapshot(
                    version="1.1.0",
                    spec_id="remote-dapp-api",
                    display_name="Remote dApp API",
                    source_path="api-specs/openrpc-dapp-remote-api.json",
                    contents="""
                        {
                          "openrpc": "1.2.6",
                          "info": {"title": "Remote dApp API", "version": "1.1.0"},
                          "methods": [
                            {
                              "name": "status",
                              "description": "Return remote status.",
                              "params": [],
                              "result": {
                                "name": "result",
                                "schema": {"$ref": "api-specs/openrpc-dapp-api.json#/components/schemas/StatusEvent"}
                              }
                            }
                          ],
                          "components": {"schemas": {}}
                        }
                    """,
                ),
            ],
            source_name="unit test snapshots",
            version_filter="unit test versions",
        )

        self.assertEqual(report.versions, ["1.0.0", "1.1.0"])
        specs = {spec.spec_id: spec for spec in report.specs}

        dapp_methods = {method.method: method for method in specs["dapp-api"].methods}
        self.assertEqual(dapp_methods["status"].changed_in_versions, ["1.1.0"])
        self.assertEqual(dapp_methods["connect"].introduced_version, "1.1.0")

        remote_methods = {method.method: method for method in specs["remote-dapp-api"].methods}
        self.assertEqual(remote_methods["status"].changed_in_versions, ["1.1.0"])
        self.assertIn("result updated (required fields)", remote_methods["status"].change_details[0]["changes"])

    def test_cli_builds_openrpc_pages(self) -> None:
        manifest_path = self._write_manifest()
        output_dir = self.root / "out"

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = cli_main(
                [
                    "openrpc",
                    "build-api-pages-from-manifest",
                    "--manifest",
                    str(manifest_path),
                    "--output-dir",
                    str(output_dir),
                    "--overview-title",
                    "Wallet Gateway OpenRPC",
                ]
            )

        self.assertEqual(exit_code, 0, stdout.getvalue())
        overview = (output_dir / "index.mdx").read_text(encoding="utf-8")
        dapp_page = (output_dir / "specs" / "dapp-api.mdx").read_text(encoding="utf-8")
        status_page = (output_dir / "operations" / "dapp-api" / "status.mdx").read_text(encoding="utf-8")
        remote_page = (output_dir / "operations" / "remote-dapp-api" / "status.mdx").read_text(encoding="utf-8")

        self.assertIn("Wallet Gateway OpenRPC", overview)
        self.assertIn('class="x2mdx-ref-card"', overview)
        self.assertIn("## Specs", overview)
        self.assertIn("## Methods", dapp_page)
        self.assertIn("Method pages are the primary reference surface", dapp_page)
        self.assertIn("## Protocol Details", status_page)
        self.assertIn("## Inputs", status_page)
        self.assertIn("## Outputs", status_page)
        self.assertIn("x2mdx-ref-breadcrumbs", status_page)
        self.assertIn('<h1 class="x2mdx-ref-title">status</h1>', status_page)
        self.assertNotIn("x2mdx-ref-summary", status_page)
        self.assertIn("x2mdx-ref-operation-bar", status_page)
        self.assertIn("JSON-RPC", status_page)
        self.assertNotIn("## Overview", status_page)
        self.assertIn("curl", status_page)
        self.assertIn("<JSON_RPC_URL>", status_page)
        self.assertIn("## Related Schemas", status_page)
        self.assertEqual(status_page.count('class="x2mdx-ref-schema"'), 1)
        self.assertIn("required fields", remote_page)

    def test_cli_uses_root_relative_link_prefix_for_overview_and_spec_links(self) -> None:
        manifest_path = self._write_manifest()
        output_dir = self.root / "out"

        exit_code = cli_main(
            [
                "openrpc",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(output_dir),
                "--overview-title",
                "Wallet Gateway OpenRPC",
                "--link-prefix",
                "/reference/wallet-gateway-json-rpc",
            ]
        )

        self.assertEqual(exit_code, 0)
        overview = (output_dir / "index.mdx").read_text(encoding="utf-8")
        spec_page = (output_dir / "specs" / "dapp-api.mdx").read_text(encoding="utf-8")
        operation_page = (output_dir / "operations" / "dapp-api" / "status.mdx").read_text(encoding="utf-8")

        self.assertIn('href="/reference/wallet-gateway-json-rpc/specs/dapp-api"', overview)
        self.assertIn('href="/reference/wallet-gateway-json-rpc/index"', spec_page)
        self.assertIn('href="/reference/wallet-gateway-json-rpc/specs/dapp-api"', operation_page)
        self.assertIn("x2mdx-ref-right-rail", operation_page)
        self.assertIn("x2mdx-ref-rail-panel", operation_page)
        self.assertIn("```bash cURL", operation_page)
        self.assertNotIn("## Examples", operation_page)

    def test_method_adapter_builds_operation_page_context(self) -> None:
        method = self._snapshot(
            version="1.1.0",
            spec_id="dapp-api",
            display_name="Dapp API",
            source_path="api-specs/openrpc-dapp-api.json",
            contents="""
                {
                  "openrpc": "1.2.6",
                  "info": {"title": "Dapp API", "version": "1.1.0"},
                  "methods": [
                    {
                      "name": "status",
                      "description": "Return wallet provider status.",
                      "params": [],
                      "result": {
                        "name": "result",
                        "schema": {"type": "object", "required": ["connected"], "properties": {"connected": {"type": "boolean"}}}
                      }
                    }
                  ]
                }
            """,
        )
        report = build_openrpc_report_from_sources(
            [method],
            source_name="unit test snapshots",
            version_filter="unit test versions",
            publish_version="1.1.0",
        )
        spec = report.specs[0]
        page = build_method_page(spec, spec.methods[0], output_dir=self.root / "out", spec_dir_name="specs")

        self.assertEqual(page.path, "operations/dapp-api/status.mdx")
        self.assertEqual(page.badges[0].label, "JSON-RPC")
        self.assertEqual(page.operation_method, "POST")
        self.assertEqual(page.operation_target, "JSON-RPC status")
        self.assertEqual(page.related_schemas[0].name, "result")
        self.assertEqual(page.outputs[0].schema.name, "result")
        self.assertEqual(page.examples[0].title, "cURL")
        self.assertIn('"method": "status"', page.examples[0].body)
        self.assertEqual(page.examples[1].title, "Result")
