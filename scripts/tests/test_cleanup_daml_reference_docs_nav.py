import json
import tempfile
import unittest
from pathlib import Path

from scripts.cleanup_daml_reference_docs_nav import cleanup_navigation


class CleanupDamlReferenceDocsNavTests(unittest.TestCase):
    def test_removes_reference_dropdown_and_legacy_groups(self) -> None:
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
                                                {
                                                    "group": "Generated API Reference",
                                                    "pages": ["old"],
                                                },
                                                {
                                                    "group": "Daml Standard Library",
                                                    "pages": ["new"],
                                                },
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "dropdown": "Daml Reference Docs",
                                    "versions": [
                                        {
                                            "version": "3.4.11",
                                            "groups": [
                                                {
                                                    "group": "Daml Standard Library",
                                                    "pages": ["legacy"],
                                                }
                                            ],
                                        }
                                    ],
                                },
                            ]
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            removed_dropdowns, removed_legacy_groups = cleanup_navigation(
                docs_json_path=docs_json,
                remove_dropdown_name="Daml Reference Docs",
                appdev_dropdown_name="App Development",
                remove_legacy_group_name="Generated API Reference",
            )

            self.assertEqual(removed_dropdowns, 1)
            self.assertEqual(removed_legacy_groups, 1)

            with docs_json.open("r", encoding="utf-8") as handle:
                updated = json.load(handle)

            dropdowns = updated["navigation"]["dropdowns"]
            self.assertEqual(len(dropdowns), 1)
            self.assertEqual(dropdowns[0]["dropdown"], "App Development")
            groups = dropdowns[0]["versions"][0]["groups"]
            self.assertTrue(all(g["group"] != "Generated API Reference" for g in groups))
            self.assertTrue(any(g["group"] == "Daml Standard Library" for g in groups))


if __name__ == "__main__":
    unittest.main()
