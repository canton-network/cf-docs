import unittest
from pathlib import Path

from scripts.diff_daml_docs_json import (
    compute_schema_diff,
    compute_semantic_diff,
    load_modules,
)


class DiffDamlDocsJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        fixtures = Path(__file__).parent / "fixtures"
        self.old_modules = load_modules(fixtures / "sample_prim_diff_old.json")
        self.new_modules = load_modules(fixtures / "sample_prim_diff_new.json")

    def test_semantic_diff_detects_api_changes(self) -> None:
        semantic = compute_semantic_diff(self.old_modules, self.new_modules)

        self.assertEqual(semantic["functions"]["added"], ["Prelude.bar"])
        self.assertEqual(semantic["functions"]["removed"], [])
        self.assertEqual(semantic["functions"]["changed"], ["Prelude.foo"])

        self.assertEqual(semantic["class_methods"]["added"], [])
        self.assertEqual(semantic["class_methods"]["removed"], [])
        self.assertEqual(
            semantic["class_methods"]["changed"], ["Prelude.EqLike.eqLike"]
        )

    def test_schema_diff_detects_format_and_key_changes(self) -> None:
        schema = compute_schema_diff(self.old_modules, self.new_modules)

        type_changes_by_path = {
            change["path"]: (change["old_types"], change["new_types"])
            for change in schema["type_changes"]
        }
        self.assertIn("$[].md_functions[].fct_descr", type_changes_by_path)
        self.assertEqual(
            type_changes_by_path["$[].md_functions[].fct_descr"],
            (["string"], ["array"]),
        )
        self.assertIn("$[].md_adts[].TypeSynDoc.ad_descr", type_changes_by_path)
        self.assertEqual(
            type_changes_by_path["$[].md_adts[].TypeSynDoc.ad_descr"],
            (["string"], ["array"]),
        )

        key_changes_by_path = {change["path"]: change for change in schema["key_changes"]}
        self.assertIn("$[].md_functions[]", key_changes_by_path)
        self.assertIn("fct_warns", key_changes_by_path["$[].md_functions[]"]["added_keys"])
        self.assertIn("$[].md_adts[].TypeSynDoc", key_changes_by_path)
        self.assertIn(
            "ad_warns", key_changes_by_path["$[].md_adts[].TypeSynDoc"]["added_keys"]
        )


if __name__ == "__main__":
    unittest.main()
