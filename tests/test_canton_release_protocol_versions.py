from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts import generate_all_reference_docs  # noqa: E402
from scripts import generate_canton_release_protocol_versions as generator  # noqa: E402


class CantonReleaseProtocolVersionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.asset = generator.ReleaseAsset(
            tag="v3.5.15",
            version="3.5.15",
            name="canton-open-source-3.5.15.tar.gz",
            url="https://github.com/digital-asset/canton/releases/download/v3.5.15/canton-open-source-3.5.15.tar.gz",
            size=123,
            digest="sha256:" + "a" * 64,
        )

    def test_uses_public_release_source(self) -> None:
        self.assertEqual(generator.DEFAULT_RELEASE_REPO, "digital-asset/canton")
        self.assertNotIn(
            "DACH-NY", generator.REFERENCE_SCRIPT.read_text(encoding="utf-8")
        )

    def test_aggregate_generator_includes_release_protocol_table(self) -> None:
        job = next(
            job
            for job in generate_all_reference_docs.SCRIPT_JOBS
            if job.script_path.name == "generate_canton_release_protocol_versions.py"
        )
        self.assertEqual(job.nav_slices, ())
        self.assertEqual(job.target_ids, ())

    def test_load_rows_validates_shape(self) -> None:
        self.assertEqual(
            generator.load_rows(
                {"releaseVersionsToProtocolVersions": [["3.5", ["34", "35"]]]}
            ),
            [("3.5", ["34", "35"])],
        )
        with self.assertRaisesRegex(ValueError, "row 0"):
            generator.load_rows({"releaseVersionsToProtocolVersions": [["3.5", []]]})

    def test_render_section_includes_beta_legend_and_provenance(self) -> None:
        section = generator.render_section(
            [("2.9", ["5", "6*"]), ("3.5", ["34", "35"])],
            asset=self.asset,
        )
        self.assertIn('source="digital-asset/canton"', section)
        self.assertIn('release_line_count="2"', section)
        self.assertIn("| 3.5 | 34, 35 |", section)
        self.assertIn("trailing asterisk identifies a beta", section)

    def test_load_rows_reads_protocol_lf_rows(self) -> None:
        payload = {
            "releaseVersionsToProtocolVersions": [["3.6", ["34", "35", "36"]]],
            "protocolVersionsToLfVersions": [["34", ["2.1", "2.2"]]],
        }
        self.assertEqual(
            generator.load_rows(payload, "protocolVersionsToLfVersions"),
            [("34", ["2.1", "2.2"])],
        )
        with self.assertRaisesRegex(ValueError, "protocolVersionsToLfVersions list"):
            generator.load_rows(
                {"releaseVersionsToProtocolVersions": []}, "protocolVersionsToLfVersions"
            )

    def test_render_lf_section_lists_lf_versions_per_protocol_version(self) -> None:
        section = generator.render_lf_section(
            [("34", ["2.1", "2.2"]), ("36", ["2.1", "2.2", "2.3", "2.4"])],
            asset=self.asset,
        )
        self.assertTrue(section.startswith(generator.LF_GENERATED_START))
        self.assertIn('protocol_version_count="2"', section)
        self.assertIn("| 34 | 2.1, 2.2 |", section)
        self.assertIn("| 36 | 2.1, 2.2, 2.3, 2.4 |", section)
        self.assertNotIn("asterisk", section)
        self.assertIn(
            "asterisk",
            generator.render_lf_section([("37*", ["2.1"])], asset=self.asset),
        )

    def test_render_lf_snippet_exports_dashboard_rows(self) -> None:
        snippet = generator.render_lf_snippet(
            [("34", ["2.1", "2.2"]), ("37*", ["2.1"])], asset=self.asset
        )
        self.assertIn(
            'export const protocolLfVersionsSource = {"cantonVersion": "3.5.15", '
            '"tag": "v3.5.15"',
            snippet,
        )
        self.assertIn(
            '  {"protocolVersion": "34", "beta": false, "lfVersions": ["2.1", "2.2"]},',
            snippet,
        )
        self.assertIn('{"protocolVersion": "37", "beta": true', snippet)
        self.assertTrue(snippet.endswith("];\n"))

    def test_both_sections_coexist_and_regenerate_in_place(self) -> None:
        page = "Frontmatter\n\nExisting release guidance.\n"
        release = generator.render_section([("3.6", ["34", "35"])], asset=self.asset)
        lf = generator.render_lf_section([("34", ["2.1", "2.2"])], asset=self.asset)

        def regenerate(text: str) -> str:
            text = generator.replace_section(text, release)
            return generator.replace_section(
                text, lf, generator.LF_GENERATED_START, generator.LF_GENERATED_END
            )

        first = regenerate(page)
        second = regenerate(first)
        self.assertEqual(first, second)
        self.assertLess(
            first.index(generator.GENERATED_END),
            first.index(generator.LF_GENERATED_START),
        )

    def test_replace_section_is_idempotent_and_preserves_page(self) -> None:
        page = "Frontmatter\n\nExisting release guidance.\n"
        section = generator.render_section([("3.5", ["34", "35"])], asset=self.asset)
        first = generator.replace_section(page, section)
        second = generator.replace_section(first, section)

        self.assertEqual(first, second)
        self.assertIn("Existing release guidance.", first)
        self.assertEqual(first.count(generator.GENERATED_START), 1)


if __name__ == "__main__":
    unittest.main()
