import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.daml_docs_json_to_mdx import (
    build_nav_pages,
    load_modules,
    update_daml_reference_docs_navigation,
    update_docs_json_navigation,
    write_modules,
)


class DamlDocsJsonToMdxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixtures = Path(__file__).parent / "fixtures"

    def test_generates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "docs-main" / "appdev" / "reference" / "daml-prim-api"
            modules = load_modules(self.fixtures / "sample_prim.json")
            module_targets = write_modules(modules, out_dir)

            self.assertEqual(module_targets, ["index", "prelude", "da-stack"])
            self.assertTrue((out_dir / "index.mdx").exists())
            self.assertTrue((out_dir / "prelude.mdx").exists())
            self.assertTrue((out_dir / "da-stack.mdx").exists())

            index_content = (out_dir / "index.mdx").read_text(encoding="utf-8")
            self.assertIn("- [Prelude](./prelude)", index_content)
            self.assertIn("- [DA.Stack](./da-stack)", index_content)

    def test_updates_all_matching_generated_api_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_json = Path(tmpdir) / "docs.json"
            shutil.copy2(self.fixtures / "sample_docs.json", docs_json)

            nav_pages = build_nav_pages(
                "docs-main/appdev/reference/daml-prim-api",
                ["index", "prelude", "da-stack"],
            )
            replacements = update_docs_json_navigation(
                docs_json_path=docs_json,
                nav_group_name="Generated API Reference",
                nav_pages=nav_pages,
            )
            self.assertEqual(replacements, 2)

            with docs_json.open("r", encoding="utf-8") as f:
                updated = json.load(f)

            groups = []
            for section in updated["navigation"]:
                for version in section.get("versions", []):
                    for group in version.get("groups", []):
                        if group.get("group") == "Generated API Reference":
                            groups.append(group)
            self.assertEqual(len(groups), 2)
            for group in groups:
                self.assertEqual(group["pages"], nav_pages)

    def test_raises_when_group_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_json = Path(tmpdir) / "docs.json"
            docs_json.write_text('{"navigation":[]}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                update_docs_json_navigation(
                    docs_json_path=docs_json,
                    nav_group_name="Generated API Reference",
                    nav_pages=["docs-main/appdev/reference/daml-prim-api/index"],
                )

    def test_creates_missing_group_under_dropdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_json = Path(tmpdir) / "docs.json"
            docs_json.write_text(
                json.dumps(
                    {
                        "navigation": [
                            {
                                "dropdown": "Application Development",
                                "versions": [
                                    {
                                        "version": "MainNet",
                                        "groups": [
                                            {"group": "Module 1", "pages": ["m1"]},
                                            {"group": "Help", "pages": ["help"]},
                                        ],
                                    },
                                    {
                                        "version": "DevNet",
                                        "groups": [
                                            {"group": "Module 1", "pages": ["m1"]},
                                            {"group": "Help", "pages": ["help"]},
                                        ],
                                    },
                                ],
                            }
                        ]
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            nav_pages = build_nav_pages(
                "docs-main/appdev/reference/daml-prim-api",
                ["index", "prelude"],
            )
            replacements = update_docs_json_navigation(
                docs_json_path=docs_json,
                nav_group_name="Generated API Reference",
                nav_pages=nav_pages,
                create_nav_group_if_missing=True,
                nav_dropdown_name="Application Development",
            )
            self.assertEqual(replacements, 2)

            with docs_json.open("r", encoding="utf-8") as f:
                updated = json.load(f)

            for version in updated["navigation"][0]["versions"]:
                groups = version["groups"]
                self.assertEqual(groups[-2]["group"], "Generated API Reference")
                self.assertEqual(groups[-2]["pages"], nav_pages)
                self.assertEqual(groups[-1]["group"], "Help")

    def test_create_group_requires_dropdown_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_json = Path(tmpdir) / "docs.json"
            docs_json.write_text('{"navigation":[]}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                update_docs_json_navigation(
                    docs_json_path=docs_json,
                    nav_group_name="Generated API Reference",
                    nav_pages=["docs-main/appdev/reference/daml-prim-api/index"],
                    create_nav_group_if_missing=True,
                )

    def test_upserts_daml_reference_docs_and_removes_legacy_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_json = Path(tmpdir) / "docs.json"
            docs_json.write_text(
                json.dumps(
                    {
                        "navigation": {
                            "dropdowns": [
                                {
                                    "dropdown": "App Development",
                                    "versions": [
                                        {
                                            "version": "MainNet",
                                            "groups": [
                                                {"group": "Module 1", "pages": ["m1"]},
                                                {"group": "Generated API Reference", "pages": ["old"]},
                                                {"group": "Help", "pages": ["help"]},
                                            ],
                                        },
                                        {
                                            "version": "DevNet",
                                            "groups": [
                                                {"group": "Generated API Reference", "pages": ["old"]},
                                            ],
                                        },
                                    ],
                                },
                                {
                                    "dropdown": "Global Synchronizer",
                                    "versions": [],
                                },
                            ]
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            removed_legacy, updated_existing = update_daml_reference_docs_navigation(
                docs_json_path=docs_json,
                version_entries=[
                    {
                        "version": "3.4.11",
                        "pages": [
                            "docs-main/daml-reference/daml-prim-api/v3-4-11/index",
                            "docs-main/daml-reference/daml-prim-api/v3-4-11/prelude",
                        ],
                    },
                    {
                        "version": "3.4.10",
                        "pages": [
                            "docs-main/daml-reference/daml-prim-api/v3-4-10/index",
                        ],
                    },
                ],
            )

            self.assertEqual(removed_legacy, 2)
            self.assertFalse(updated_existing)

            with docs_json.open("r", encoding="utf-8") as f:
                updated = json.load(f)

            app_dev = updated["navigation"]["dropdowns"][0]
            for version in app_dev["versions"]:
                groups = version["groups"]
                self.assertTrue(all(g["group"] != "Generated API Reference" for g in groups))

            daml_ref = updated["navigation"]["dropdowns"][1]
            self.assertEqual(daml_ref["dropdown"], "Daml Reference Docs")
            self.assertEqual(daml_ref["icon"], "book-open")
            self.assertEqual([v["version"] for v in daml_ref["versions"]], ["3.4.11", "3.4.10"])
            self.assertEqual(daml_ref["versions"][0]["groups"][0]["group"], "Daml Prim API")

    def test_replaces_existing_daml_reference_docs_dropdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_json = Path(tmpdir) / "docs.json"
            docs_json.write_text(
                json.dumps(
                    {
                        "navigation": {
                            "dropdowns": [
                                {
                                    "dropdown": "App Development",
                                    "versions": [],
                                },
                                {
                                    "dropdown": "Daml Reference Docs",
                                    "icon": "book-old",
                                    "versions": [{"version": "old", "groups": [{"group": "x", "pages": ["y"]}]}],
                                },
                                {
                                    "dropdown": "Daml Reference Docs",
                                    "icon": "duplicate",
                                    "versions": [],
                                },
                            ]
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            removed_legacy, updated_existing = update_daml_reference_docs_navigation(
                docs_json_path=docs_json,
                version_entries=[
                    {
                        "version": "3.4.11",
                        "pages": ["docs-main/daml-reference/daml-prim-api/v3-4-11/index"],
                    }
                ],
            )

            self.assertEqual(removed_legacy, 0)
            self.assertTrue(updated_existing)

            with docs_json.open("r", encoding="utf-8") as f:
                updated = json.load(f)

            refs = [
                s
                for s in updated["navigation"]["dropdowns"]
                if s.get("dropdown") == "Daml Reference Docs"
            ]
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0]["icon"], "book-open")
            self.assertEqual(refs[0]["versions"][0]["version"], "3.4.11")


if __name__ == "__main__":
    unittest.main()
