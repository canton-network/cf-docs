import unittest

from scripts.list_latest_release_versions_by_family import parse_families, select_versions


class ListLatestReleaseVersionsByFamilyTests(unittest.TestCase):
    def test_parse_families(self) -> None:
        self.assertEqual(parse_families("3.4,3.3,3.2"), [(3, 4), (3, 3), (3, 2)])
        self.assertEqual(parse_families("3.4, 3.4, 3.3"), [(3, 4), (3, 3)])

    def test_select_versions_by_family(self) -> None:
        versions = [
            "3.4.11",
            "3.4.10",
            "3.4.9",
            "3.4.8",
            "3.3.0-snapshot.20250930.0",
            "3.3.0-snapshot.20250305.0",
            "3.3.0-snapshot.20250101.0",
            "3.2.0-snapshot.20250206.0",
            "3.2.0-snapshot.20241023.0",
            "3.2.0-snapshot.20240801.0",
            "3.1.9",
        ]
        selected, warnings = select_versions(
            versions=versions,
            families=[(3, 4), (3, 3), (3, 2)],
            count_per_family=3,
        )
        self.assertEqual(
            selected,
            [
                "3.4.11",
                "3.4.10",
                "3.4.9",
                "3.3.0-snapshot.20250930.0",
                "3.3.0-snapshot.20250305.0",
                "3.3.0-snapshot.20250101.0",
                "3.2.0-snapshot.20250206.0",
                "3.2.0-snapshot.20241023.0",
                "3.2.0-snapshot.20240801.0",
            ],
        )
        self.assertEqual(warnings, [])

    def test_warns_when_family_has_fewer_versions(self) -> None:
        versions = ["3.4.11", "3.4.10", "3.4.9"]
        selected, warnings = select_versions(
            versions=versions,
            families=[(3, 4), (3, 3), (3, 2)],
            count_per_family=3,
        )
        self.assertEqual(selected, ["3.4.11", "3.4.10", "3.4.9"])
        self.assertEqual(len(warnings), 2)
        self.assertIn("3.3.x", warnings[0])
        self.assertIn("3.2.x", warnings[1])


if __name__ == "__main__":
    unittest.main()
