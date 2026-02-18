import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.daml_docs_json_to_mdx import (
    build_nav_pages,
    load_modules,
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


if __name__ == "__main__":
    unittest.main()
