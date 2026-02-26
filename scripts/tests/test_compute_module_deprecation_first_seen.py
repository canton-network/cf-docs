import json
import tempfile
import unittest
from pathlib import Path

from scripts.compute_module_deprecation_first_seen import (
    compute_first_seen_map,
    parse_version_json_inputs,
)


class ComputeModuleDeprecationFirstSeenTests(unittest.TestCase):
    def test_picks_first_seen_version_after_sorting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            v_330 = root / "v330.json"
            v_340 = root / "v340.json"
            v_341 = root / "v341.json"

            v_330.write_text(
                json.dumps(
                    [
                        {"md_name": "DA.Exception"},
                        {"md_name": "Prelude"},
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            v_340.write_text(
                json.dumps(
                    [
                        {
                            "md_name": "DA.Exception",
                            "md_warn": {
                                "DeprecatedData": [
                                    "Exceptions are deprecated.",
                                ]
                            },
                        }
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            v_341.write_text(
                json.dumps(
                    [
                        {
                            "md_name": "DA.Exception",
                            "md_warn": {
                                "DeprecatedData": [
                                    "Exceptions are deprecated.",
                                ]
                            },
                        }
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            parsed = parse_version_json_inputs(
                [
                    f"3.4.11={v_341}",
                    f"3.3.0-snapshot.20250930.0={v_330}",
                    f"3.4.9={v_340}",
                ]
            )
            first_seen = compute_first_seen_map(parsed)
            self.assertEqual(first_seen, {"DA.Exception": "3.4.9"})


if __name__ == "__main__":
    unittest.main()
