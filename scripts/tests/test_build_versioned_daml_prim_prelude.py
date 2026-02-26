import tempfile
import unittest
from pathlib import Path

from scripts.build_versioned_daml_prim_prelude import (
    VersionInput,
    build_enriched_index,
    render_unified_mdx,
)


class BuildVersionedDamlPrimPreludeTests(unittest.TestCase):
    def setUp(self) -> None:
        fixtures = Path(__file__).parent / "fixtures"
        self.inputs = [
            VersionInput("3.2.0-snapshot", fixtures / "sample_prim_diff_old.json"),
            VersionInput("3.4.11", fixtures / "sample_prim_diff_new.json"),
        ]

    def test_builds_enriched_index_with_timeline(self) -> None:
        index = build_enriched_index(self.inputs, module_name="Prelude")

        self.assertEqual(index["schema_version"], "daml-prim-version-index/v2")
        self.assertEqual([item["id"] for item in index["versions"]], ["3.2.0-snapshot", "3.4.11"])

        by_id = {element["id"]: element for element in index["elements"]}
        self.assertIn("function:Prelude.foo", by_id)
        self.assertIn("function:Prelude.bar", by_id)
        self.assertIn("class_method:Prelude.EqLike.eqLike", by_id)

        foo = by_id["function:Prelude.foo"]
        self.assertEqual(foo["introduced_in"], "3.2.0-snapshot")
        self.assertEqual(foo["removed_in"], None)
        self.assertEqual(foo["changed_versions"], ["3.4.11"])
        self.assertEqual(foo["semantic_changed_versions"], ["3.4.11"])
        self.assertEqual(foo["deprecation_changed_versions"], [])
        self.assertGreaterEqual(len(foo["timeline"]), 2)

        bar = by_id["function:Prelude.bar"]
        self.assertEqual(bar["introduced_in"], "3.4.11")
        self.assertEqual(bar["status"], "active")

        self.assertEqual(index["summary"]["function"]["added_after_baseline"], 1)
        self.assertEqual(index["summary"]["function"]["semantic_changed"], 1)
        self.assertEqual(index["summary"]["function"]["deprecation_changed"], 0)

    def test_renders_unified_mdx(self) -> None:
        index = build_enriched_index(self.inputs, module_name="Prelude")
        mdx = render_unified_mdx(index)

        self.assertIn('title: "Prelude API Across Versions"', mdx)
        self.assertIn("Compared versions: `3.2.0-snapshot`, `3.4.11`", mdx)
        self.assertIn("## Module Snapshot", mdx)
        self.assertIn("<CardGroup cols={3}>", mdx)
        self.assertIn("First seen in `3.2.0-snapshot`", mdx)
        self.assertIn("`active`", mdx)
        self.assertIn("Present in latest `3.4.11`", mdx)
        self.assertIn("## Function Index", mdx)
        self.assertIn("`foo`", mdx)
        self.assertIn("`bar`", mdx)
        self.assertIn("Added In", mdx)
        self.assertIn("Signature Changed In", mdx)
        self.assertIn("Deprecation Changed In", mdx)
        self.assertIn("Change details:", mdx)
        self.assertIn("Signature changed: `3.2.0-snapshot` -> `3.4.11`", mdx)
        self.assertIn("foo : Int", mdx)
        self.assertIn("foo : Int64", mdx)

    def test_can_write_generated_outputs(self) -> None:
        index = build_enriched_index(self.inputs, module_name="Prelude")
        mdx = render_unified_mdx(index)
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "prelude-versioned.mdx"
            out.write_text(mdx, encoding="utf-8")
            self.assertTrue(out.exists())

    def test_handles_module_missing_in_older_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_json = Path(tmpdir) / "old.json"
            new_json = Path(tmpdir) / "new.json"
            old_json.write_text("[]\n", encoding="utf-8")
            new_json.write_text(
                """
[
  {
    "md_name": "DA.Crypto.Text",
    "md_descr": [],
    "md_functions": [
      {
        "fct_name": "sha256",
        "fct_context": [],
        "fct_type": {
          "TypeFun": [
            "Text",
            "Text"
          ]
        },
        "fct_descr": [],
        "fct_warns": []
      }
    ],
    "md_adts": [],
    "md_classes": [],
    "md_instances": []
  }
]
""".strip()
                + "\n",
                encoding="utf-8",
            )

            index = build_enriched_index(
                [
                    VersionInput("old", old_json),
                    VersionInput("new", new_json),
                ],
                module_name="DA.Crypto.Text",
            )
            by_id = {element["id"]: element for element in index["elements"]}
            self.assertIn("function:DA.Crypto.Text.sha256", by_id)
            self.assertEqual(by_id["function:DA.Crypto.Text.sha256"]["introduced_in"], "new")

    def test_renders_alpha_module_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_json = Path(tmpdir) / "old.json"
            new_json = Path(tmpdir) / "new.json"
            old_json.write_text("[]\n", encoding="utf-8")
            new_json.write_text(
                """
[
  {
    "md_name": "DA.Crypto.Text",
    "md_descr": [],
    "md_warn": {
      "WarnData": [
        "DA.Crypto.Text is an alpha feature. It can change without notice."
      ]
    },
    "md_functions": [],
    "md_adts": [],
    "md_classes": [],
    "md_instances": []
  }
]
""".strip()
                + "\n",
                encoding="utf-8",
            )
            index = build_enriched_index(
                [
                    VersionInput("3.4.9", old_json),
                    VersionInput("3.4.11", new_json),
                ],
                module_name="DA.Crypto.Text",
            )
            mdx = render_unified_mdx(index)
            self.assertIn("## Module Snapshot", mdx)
            self.assertIn("Alpha (experimental).", mdx)
            self.assertIn("First seen in `3.4.11`", mdx)
            self.assertIn("`3.4.x`", mdx)
            self.assertIn("Present in latest `3.4.11`", mdx)

    def test_renders_removed_module_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_json = Path(tmpdir) / "old.json"
            new_json = Path(tmpdir) / "new.json"
            old_json.write_text(
                """
[
  {
    "md_name": "DA.Crypto",
    "md_descr": [],
    "md_functions": [],
    "md_adts": [],
    "md_classes": [],
    "md_instances": []
  }
]
""".strip()
                + "\n",
                encoding="utf-8",
            )
            new_json.write_text("[]\n", encoding="utf-8")

            index = build_enriched_index(
                [
                    VersionInput("3.3.0-snapshot.20250305.0", old_json),
                    VersionInput("3.3.0-snapshot.20250930.0", new_json),
                ],
                module_name="DA.Crypto",
            )
            mdx = render_unified_mdx(index)
            self.assertIn("`removed`", mdx)
            self.assertIn("Removed in `3.3.0-snapshot.20250930.0`", mdx)


if __name__ == "__main__":
    unittest.main()
