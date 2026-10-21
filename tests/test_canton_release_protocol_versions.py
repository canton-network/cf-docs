from __future__ import annotations

from pathlib import Path
import sys
import tempfile
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

    def row(self, protocol, versions, *, beta=False, by="v3.5.15", carried=False):
        return generator.LfRow(
            protocol_version=protocol,
            beta=beta,
            lf_versions=versions,
            last_reported_by=by,
            carried_forward=carried,
        )

    def test_probed_lf_rows_parse_beta_labels(self) -> None:
        self.assertEqual(
            generator.probed_lf_rows([("37*", ["2.5"]), ("36", ["2.4"])], asset=self.asset),
            [self.row(37, ["2.5"], beta=True), self.row(36, ["2.4"])],
        )

    def test_render_lf_section_lists_lf_versions_per_protocol_version(self) -> None:
        section = generator.render_lf_section(
            [self.row(36, ["2.4", "2.3", "2.2", "2.1"]), self.row(34, ["2.2", "2.1"])],
            asset=self.asset,
        )
        self.assertTrue(section.startswith(generator.LF_GENERATED_START))
        self.assertIn('ref="v3.5.15"', section)
        self.assertIn('protocol_version_count="2"', section)
        self.assertIn("The public Canton 3.5.15 release reports", section)
        self.assertIn("| 36 | 2.4, 2.3, 2.2, 2.1 |", section)
        self.assertIn("| 34 | 2.2, 2.1 |", section)
        self.assertNotIn("asterisk", section)
        self.assertNotIn(generator.CARRIED_FORWARD_MARK, section)

    def test_render_lf_section_marks_beta_and_carried_rows(self) -> None:
        section = generator.render_lf_section(
            [
                self.row(37, ["2.5"], beta=True),
                self.row(34, ["2.2", "2.1"], by="v3.4.9", carried=True),
            ],
            asset=self.asset,
        )
        self.assertIn("| 37* | 2.5 |", section)
        self.assertIn("| 34 † | 2.2, 2.1 |", section)
        self.assertIn("asterisk", section)
        self.assertIn("† Not supported by Canton 3.5.15.", section)

    def test_render_lf_snippet_exports_dashboard_rows(self) -> None:
        snippet = generator.render_lf_snippet(
            [
                self.row(37, ["2.5"], beta=True),
                self.row(34, ["2.2", "2.1"], by="v3.4.9", carried=True),
            ],
            asset=self.asset,
        )
        self.assertIn(
            'export const protocolLfVersionsSource = {"cantonVersion": "3.5.15", '
            '"tag": "v3.5.15"',
            snippet,
        )
        self.assertIn(
            '  {"protocolVersion": "34", "beta": false, "lfVersions": ["2.2", "2.1"], '
            '"lastReportedBy": "v3.4.9", "carriedForward": true},',
            snippet,
        )
        self.assertIn('{"protocolVersion": "37", "beta": true', snippet)
        self.assertTrue(snippet.endswith("];\n"))

    def test_published_rows_round_trip_through_the_snippet(self) -> None:
        rows = [
            self.row(36, ["2.4", "2.3"]),
            self.row(34, ["2.2", "2.1"], by="v3.4.9", carried=True),
        ]
        with tempfile.TemporaryDirectory() as directory:
            snippet = Path(directory) / "protocol-lf-versions.mdx"
            self.assertEqual(generator.load_published_lf_rows(snippet), [])
            snippet.write_text(
                generator.render_lf_snippet(rows, asset=self.asset), encoding="utf-8"
            )
            self.assertEqual(generator.load_published_lf_rows(snippet), rows)

    def test_load_published_lf_rows_rejects_unreadable_snippets(self) -> None:
        valid = generator.render_lf_snippet([self.row(36, ["2.4"])], asset=self.asset)
        broken = {
            "reformatted row": valid.replace(
                '  {"protocolVersion": "36"', "  {\n    protocolVersion: '36'"
            ),
            "missing export": valid.replace("protocolLfVersions = [", "rows = ["),
            "empty rows": valid.replace(
                valid[valid.index("  {") : valid.index("];")], ""
            ),
            "missing field": valid.replace('"beta": false, ', ""),
        }
        with tempfile.TemporaryDirectory() as directory:
            snippet = Path(directory) / "protocol-lf-versions.mdx"
            for name, text in broken.items():
                with self.subTest(name):
                    snippet.write_text(text, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "protocolLfVersions"):
                        generator.load_published_lf_rows(snippet)

    def test_carry_forward_keeps_stable_rows_the_release_dropped(self) -> None:
        probed = [self.row(37, ["2.5", "2.4"]), self.row(36, ["2.4", "2.3"])]
        published = [
            self.row(36, ["2.4", "2.3"], by="v3.4.9"),
            self.row(35, ["2.3", "2.2"], by="v3.4.9"),
            self.row(34, ["2.2", "2.1"], by="v3.3.1", carried=True),
        ]
        self.assertEqual(
            generator.carry_forward_lf_rows(probed, published, asset=self.asset),
            [
                self.row(37, ["2.5", "2.4"]),
                self.row(36, ["2.4", "2.3"]),
                self.row(35, ["2.3", "2.2"], by="v3.4.9", carried=True),
                self.row(34, ["2.2", "2.1"], by="v3.3.1", carried=True),
            ],
        )

    def test_carry_forward_restores_a_row_the_release_reports_again(self) -> None:
        probed = [self.row(35, ["2.3", "2.2"])]
        published = [self.row(35, ["2.3", "2.2"], by="v3.4.9", carried=True)]
        self.assertEqual(
            generator.carry_forward_lf_rows(probed, published, asset=self.asset),
            [self.row(35, ["2.3", "2.2"])],
        )

    def test_carry_forward_drops_beta_rows_and_accepts_beta_changes(self) -> None:
        probed = [self.row(37, ["2.5", "2.4"], beta=True)]
        published = [
            self.row(37, ["2.4"], beta=True, by="v3.4.9"),
            self.row(38, ["2.6"], beta=True, by="v3.4.9"),
        ]
        self.assertEqual(
            generator.carry_forward_lf_rows(probed, published, asset=self.asset),
            [self.row(37, ["2.5", "2.4"], beta=True)],
        )

    def test_carry_forward_rejects_a_changed_stable_row(self) -> None:
        probed = [self.row(35, ["2.3"])]
        published = [self.row(35, ["2.3", "2.2"], by="v3.4.9")]
        with self.assertRaisesRegex(
            ValueError, r"Protocol version 35: v3.4.9 reported \['2.3', '2.2'\]"
        ):
            generator.carry_forward_lf_rows(probed, published, asset=self.asset)

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
