from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts import generate_all_reference_docs  # noqa: E402
from scripts import canton_release_reference  # noqa: E402
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
        self.older = generator.ReleaseAsset(
            tag="v3.4.9",
            version="3.4.9",
            name="canton-open-source-3.4.9.tar.gz",
            url="https://github.com/digital-asset/canton/releases/download/v3.4.9/canton-open-source-3.4.9.tar.gz",
            size=456,
            digest="sha256:" + "b" * 64,
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
            [("36", ["2.4", "2.3", "2.2", "2.1"]), ("34", ["2.2", "2.1"])],
            assets=[self.asset, self.older],
        )
        self.assertTrue(section.startswith(generator.LF_GENERATED_START))
        self.assertIn('protocol_version_count="2"', section)
        self.assertIn('refs="v3.5.15 v3.4.9"', section)
        self.assertIn("The public Canton 3.5.15 and 3.4.9 releases report", section)
        self.assertIn("| 36 | 2.4, 2.3, 2.2, 2.1 |", section)
        self.assertIn("| 34 | 2.2, 2.1 |", section)
        self.assertNotIn("asterisk", section)
        single = generator.render_lf_section([("37*", ["2.1"])], assets=[self.asset])
        self.assertIn("asterisk", single)
        self.assertIn("The public Canton 3.5.15 release reports", single)

    def test_render_lf_snippet_exports_dashboard_rows(self) -> None:
        snippet = generator.render_lf_snippet(
            [("34", ["2.1", "2.2"]), ("37*", ["2.1"])], assets=[self.asset, self.older]
        )
        self.assertIn(
            'export const protocolLfVersionsSource = {"releases": [{"cantonVersion": "3.5.15", '
            '"tag": "v3.5.15"',
            snippet,
        )
        self.assertIn('{"cantonVersion": "3.4.9", "tag": "v3.4.9"', snippet)
        self.assertIn(
            '  {"protocolVersion": "34", "beta": false, "lfVersions": ["2.1", "2.2"]},',
            snippet,
        )
        self.assertIn('{"protocolVersion": "37", "beta": true', snippet)
        self.assertTrue(snippet.endswith("];\n"))

    def test_both_sections_coexist_and_regenerate_in_place(self) -> None:
        page = "Frontmatter\n\nExisting release guidance.\n"
        release = generator.render_section([("3.6", ["34", "35"])], asset=self.asset)
        lf = generator.render_lf_section([("34", ["2.1", "2.2"])], assets=[self.asset])

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

    def test_merge_lf_rows_unions_release_lines_newest_protocol_first(self) -> None:
        merged = generator.merge_lf_rows(
            [
                (self.asset, [("36", ["2.4", "2.3"]), ("35", ["2.3", "2.2"])]),
                (self.older, [("35", ["2.3", "2.2"]), ("34", ["2.2", "2.1"])]),
            ]
        )
        self.assertEqual(
            merged,
            [("36", ["2.4", "2.3"]), ("35", ["2.3", "2.2"]), ("34", ["2.2", "2.1"])],
        )

    def test_merge_lf_rows_prefers_stable_label_over_beta(self) -> None:
        merged = generator.merge_lf_rows(
            [(self.asset, [("36", ["2.4"])]), (self.older, [("36*", ["2.4"])])]
        )
        self.assertEqual(merged, [("36", ["2.4"])])
        merged = generator.merge_lf_rows(
            [(self.asset, [("36*", ["2.4"])]), (self.older, [("36", ["2.4"])])]
        )
        self.assertEqual(merged, [("36", ["2.4"])])

    def test_merge_lf_rows_rejects_disagreeing_release_lines(self) -> None:
        with self.assertRaisesRegex(ValueError, "Protocol version 35: v3.5.15 reports"):
            generator.merge_lf_rows(
                [
                    (self.asset, [("35", ["2.3", "2.2"])]),
                    (self.older, [("35", ["2.2"])]),
                ]
            )

    def test_older_release_lines_use_the_legacy_probe(self) -> None:
        self.assertLess(
            generator.release_line(self.older), generator.LEGACY_LF_RELEASE_LINES_BEFORE
        )
        self.assertTrue(generator.LEGACY_LF_REFERENCE_SCRIPT.is_file())

    def test_select_latest_patch_tags_picks_newest_patch_per_line(self) -> None:
        releases = [
            {"tag_name": "v3.6.2"},
            {"tag_name": "v3.6.3"},
            {"tag_name": "v3.7.0", "prerelease": True},
            {"tag_name": "v3.5.19"},
            {"tag_name": "v3.5.9"},
            {"tag_name": "v3.4.11"},
            {"tag_name": "v3.6.4-rc1"},
            {"tag_name": "v3.6.9", "draft": True},
        ]
        self.assertEqual(
            canton_release_reference.select_latest_patch_tags(releases, line_count=2),
            ["v3.6.3", "v3.5.19"],
        )
        with self.assertRaisesRegex(ValueError, "No stable Canton releases"):
            canton_release_reference.select_latest_patch_tags([], line_count=2)

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
