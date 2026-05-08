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


def module_doc(
    name: str,
    description: str,
    *,
    warnings: list[str] | None = None,
    deprecations: list[str] | None = None,
) -> dict[str, object]:
    warn_items: list[dict[str, str]] = []
    for warning in warnings or []:
        warn_items.append({"WarnData": warning})
    for deprecated in deprecations or []:
        warn_items.append({"DeprecatedData": deprecated})
    return {
        "md_name": name,
        "md_descr": description,
        "md_warn": warn_items,
        "md_adts": [
            {
                "ADTDoc": {
                    "ad_anchor": "type-token",
                    "ad_name": "Token",
                    "ad_args": [],
                    "ad_descr": [["Token record docs"]],
                    "ad_warns": [],
                    "ad_constrs": [
                        {
                            "RecordC": {
                                "ac_anchor": "constr-token",
                                "ac_name": "Token",
                                "ac_descr": [],
                                "ac_fields": [
                                    {
                                        "fd_name": "owner",
                                        "fd_type": {"TypeApp": [{}, "Party", []]},
                                        "fd_descr": ["Owner party"],
                                    }
                                ],
                            }
                        }
                    ],
                    "ad_instances": [],
                }
            }
        ],
        "md_classes": [],
        "md_interfaces": [],
        "md_templates": [],
        "md_instances": [],
        "md_functions": [
            {
                "fct_name": "example",
                "fct_type": {"TypeFun": [{"TypeLit": "Int"}, {"TypeLit": "Int"}]},
                "fct_context": [],
                "fct_descr": f"{name} example function",
            }
        ],
    }


class DamlJsonMinimalLifecycleTests(unittest.TestCase):
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
        first = self._write_json(
            "1.0.0/modules.json",
            [
                module_doc("DA.Alpha", "Alpha module.", warnings=["Alpha: experimental module."]),
                module_doc("DA.Legacy", "Legacy module."),
                module_doc("DA.LooseLegacy", "Loose legacy module."),
            ],
        )
        second = self._write_json(
            "1.1.0/modules.json",
            [
                module_doc("DA.Alpha", "Alpha module.", warnings=["Alpha: experimental module."]),
                module_doc("DA.Current", "Current module."),
                module_doc("DA.Legacy", "Legacy module.", deprecations=["Replaced by: DA.Current."]),
                module_doc("DA.LooseLegacy", "Loose legacy module.", deprecations=["Use DA.Current instead."]),
            ],
        )
        return self._write_json(
            "manifest.json",
            {
                "source": "minimal daml json lifecycle fixtures",
                "publish_version": "1.1.0",
                "versions": [
                    {"version": "1.0.0", "json_path": str(first)},
                    {"version": "1.1.0", "json_path": str(second)},
                ],
            },
        )

    def _write_beta_stable_manifest(self) -> Path:
        payload = [
            module_doc("DA.Beta", "Beta module.", warnings=["Beta: preview module."]),
            module_doc("DA.Stable", "Stable module.", warnings=["Stable: supported module."]),
        ]
        modules = self._write_json("beta-stable/1.0.0/modules.json", payload)
        return self._write_json(
            "beta-stable/manifest.json",
            {
                "source": "minimal daml json beta stable fixtures",
                "publish_version": "1.0.0",
                "versions": [
                    {"version": "1.0.0", "json_path": str(modules)},
                ],
            },
        )

    def _render_pages(self, relative_output_dir: str = "daml-json") -> Path:
        manifest_path = self._write_manifest()
        output_dir = self.root / "out" / relative_output_dir
        run_x2mdx(
            [
                "daml-json",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(output_dir),
                "--overview-title",
                "Minimal Daml JSON",
                "--source-name",
                "minimal daml json lifecycle fixtures",
                "--version-filter",
                "minimal versions",
                "--link-prefix",
                "/reference/daml-json",
            ]
        )
        return output_dir

    def test_cli_renders_minimal_source_contract(self) -> None:
        output_dir = self._render_pages()

        self.assertEqual(
            mdx_file_set(output_dir),
            {
                "index.mdx",
                "da-alpha.mdx",
                "da-current.mdx",
                "da-legacy.mdx",
                "da-looselegacy.mdx",
            },
        )
        assert_text_tree_matches_fixture(output_dir, "daml_json/default")

        overview = read_mdx(output_dir, "index.mdx")
        alpha = read_mdx(output_dir, "da-alpha.mdx")

        assert_contains_all(
            overview,
            [
                "[`DA.Alpha`](/reference/daml-json/da-alpha)",
                "[`DA.Current`](/reference/daml-json/da-current)",
                "`1.1.0`",
            ],
        )
        assert_contains_all(alpha, ["Lifecycle", "Alpha (experimental).", "Alpha: experimental module.", "### `data Token`"])
        assert_contains_none(alpha, ["WarnData", "ADTDoc", "RecordC", "TypeFun"])

    def test_cli_renders_explicit_lifecycle_states(self) -> None:
        # TODO(https://github.com/digital-asset/docs/issues/341): define the
        # Daml JSON source convention for beta and stable lifecycle states.
        manifest_path = self._write_beta_stable_manifest()
        output_dir = self.root / "out" / "daml-json-lifecycle"

        run_x2mdx(
            [
                "daml-json",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(output_dir),
                "--overview-title",
                "Minimal Daml JSON Beta Stable",
            ]
        )

        beta = read_mdx(output_dir, "da-beta.mdx")
        stable = read_mdx(output_dir, "da-stable.mdx")
        assert_text_tree_matches_fixture(output_dir, "daml_json/beta_stable")
        assert_contains_all(beta, ["Lifecycle", "Beta (preview).", "Beta: preview module."])
        assert_contains_all(stable, ["Lifecycle", "Stable.", "Stable: supported module."])

    def test_cli_renders_replacement_metadata(self) -> None:
        output_dir = self._render_pages("daml-json-replacements")

        assert_text_tree_matches_fixture(output_dir, "daml_json/default")
        legacy = read_mdx(output_dir, "da-legacy.mdx")
        loose_legacy = read_mdx(output_dir, "da-looselegacy.mdx")
        assert_contains_all(
            legacy,
            [
                "Lifecycle",
                "Deprecated.",
                "Deprecated since: `1.1.0`",
                "Replaced by: DA.Current.",
                "Replaces: `DA.Current`",
            ],
        )
        assert_contains_all(loose_legacy, ["Use DA.Current instead."])
        assert_contains_none(loose_legacy, ["Replaces: `DA.Current`"])
        assert_contains_none(legacy + loose_legacy, ["DeprecatedData", "ADTDoc", "RecordC", "TypeFun"])

    def test_cli_prunes_stale_output(self) -> None:
        manifest_path = self._write_manifest()
        output_dir = self.root / "out" / "daml-json-prune"
        stale_file = output_dir / "stale.mdx"
        stale_file.parent.mkdir(parents=True, exist_ok=True)
        stale_file.write_text("stale\n", encoding="utf-8")

        run_x2mdx(
            [
                "daml-json",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--output-dir",
                str(output_dir),
            ]
        )

        self.assertFalse(stale_file.exists())
        assert_text_tree_matches_fixture(output_dir, "daml_json/prune")

    @unittest.skip("daml-json CLI does not expose docs-json navigation flags")
    def test_cli_updates_docs_json_navigation_idempotently(self) -> None:
        pass
