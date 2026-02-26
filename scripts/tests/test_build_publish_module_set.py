import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_publish_module_set import build_publish_modules
from scripts.compute_module_deprecation_first_seen import parse_version_json_inputs


class BuildPublishModuleSetTests(unittest.TestCase):
    def test_includes_removed_modules_from_historical_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            v_330_old = root / "v_330_old.json"
            v_330_new = root / "v_330_new.json"
            v_341 = root / "v_341.json"

            v_330_old.write_text(
                json.dumps(
                    [
                        {"md_name": "Prelude", "md_descr": [["Core functions."]]},
                        {"md_name": "DA.Crypto", "md_descr": [["Legacy crypto helpers."]]},
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            v_330_new.write_text(
                json.dumps(
                    [
                        {"md_name": "Prelude", "md_descr": [["Core functions."]]},
                        {"md_name": "DA.Crypto.Text", "md_descr": [["Text crypto helpers."]]},
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            v_341.write_text(
                json.dumps(
                    [
                        {"md_name": "Prelude", "md_descr": [["Core functions."]]},
                        {"md_name": "DA.Crypto.Text", "md_descr": [["Text crypto helpers."]]},
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            version_jsons = parse_version_json_inputs(
                [
                    f"3.3.0-snapshot.20250305.0={v_330_old}",
                    f"3.3.0-snapshot.20250507.0={v_330_new}",
                    f"3.4.11={v_341}",
                ]
            )
            merged_modules, lifecycle = build_publish_modules(version_jsons, publish_version="3.4.11")
            names = [item["md_name"] for item in merged_modules]

            self.assertIn("Prelude", names)
            self.assertIn("DA.Crypto.Text", names)
            self.assertIn("DA.Crypto", names)

            self.assertEqual(lifecycle["DA.Crypto"]["status"], "removed")
            self.assertEqual(lifecycle["DA.Crypto"]["introduced_in"], "3.3.0-snapshot.20250305.0")
            self.assertEqual(lifecycle["DA.Crypto"]["last_seen_in"], "3.3.0-snapshot.20250305.0")
            self.assertEqual(lifecycle["DA.Crypto"]["removed_in"], "3.3.0-snapshot.20250507.0")

            self.assertEqual(lifecycle["DA.Crypto.Text"]["status"], "active")
            self.assertEqual(lifecycle["DA.Crypto.Text"]["introduced_in"], "3.3.0-snapshot.20250507.0")
            self.assertEqual(lifecycle["DA.Crypto.Text"]["removed_in"], None)


if __name__ == "__main__":
    unittest.main()

