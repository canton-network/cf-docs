from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts import generate_splice_metrics_reference as generator  # noqa: E402


def metric_rst(name: str, description: str = "") -> str:
    return "\n".join(
        [
            name,
            "^" * len(name),
            f"* **Summary**: Summary of {name}.",
            f"* **Description**: {description or f'Description of {name}.'}",
            "* **Type**: gauge",
            "* **Qualification**: Debug",
            "\n",
        ]
    )


def section_rst(key: str, heading: str, *metrics: str) -> str:
    return "\n".join(
        [f".. _{key}-metrics-reference:", "", heading, "+" * len(heading), *metrics]
    )


def source_rst(**overrides: str) -> str:
    """Mirror the layout of Splice's MetricsDocs.render()."""
    sections = {
        key: section_rst(key, heading, metric_rst(f"splice.{key}.example"))
        for key, heading in generator.SECTIONS
    }
    sections.update(overrides)
    return "\n".join(
        [".. _metrics-reference:", "", "Metrics Reference", "=================", ""]
        + [sections[key] for key, _ in generator.SECTIONS]
    )


class SpliceMetricsReferenceTests(unittest.TestCase):
    def test_parses_every_section_in_upstream_order(self) -> None:
        sections = generator.parse_metrics_rst(
            source_rst(
                validator=section_rst(
                    "validator",
                    "Validator Metrics",
                    metric_rst("splice.wallet.unlocked-amulet-balance"),
                    metric_rst("splice.synchronizer-topology.num-parties"),
                )
            )
        )

        self.assertEqual(list(sections), [key for key, _ in generator.SECTIONS])
        self.assertEqual(
            [item["name"] for item in sections["validator"]],
            [
                "splice.wallet.unlocked-amulet-balance",
                "splice.synchronizer-topology.num-parties",
            ],
        )
        self.assertEqual(
            sections["sv"][0],
            {
                "name": "splice.sv.example",
                "summary": "Summary of splice.sv.example.",
                "description": "Description of splice.sv.example.",
                "type": "gauge",
                "qualification": "Debug",
            },
        )

    def test_rejects_empty_or_unknown_sections_and_incomplete_metrics(self) -> None:
        with self.assertRaisesRegex(ValueError, "no Scan Metrics"):
            generator.parse_metrics_rst(
                source_rst(scan=section_rst("scan", "Scan Metrics"))
            )
        with self.assertRaisesRegex(ValueError, "Unexpected Splice metrics section"):
            generator.parse_metrics_rst(
                source_rst(scan=section_rst("scan", "Scan Things", metric_rst("x.y")))
            )
        incomplete = "splice.sv.partial\n" + "^" * 17 + "\n* **Summary**: Only this.\n"
        with self.assertRaisesRegex(ValueError, "splice.sv.partial"):
            generator.parse_metrics_rst(
                source_rst(sv=section_rst("sv", "SV Metrics", incomplete))
            )

    def test_render_metric_escapes_mdx_and_keeps_inline_code(self) -> None:
        item = generator.MetricItem(
            name="splice.store.acs-size",
            summary="Size of the <store> ACS.",
            description="Check `batch-ingestion-latency` and {braces}.",
            type="gauge",
            qualification="Saturation",
        )

        self.assertEqual(
            generator.render_metric(item),
            [
                "### splice.store.acs-size",
                "",
                r"> - **Summary**: Size of the \<store\> ACS.",
                r"> - **Description**: Check `batch-ingestion-latency` and \{braces\}.",
                "> - **Type**: gauge",
                "> - **Qualification**: Saturation",
            ],
        )

    def test_generated_block_records_provenance_and_replaces_markers(self) -> None:
        sections = generator.parse_metrics_rst(source_rst())
        block = generator.render_generated_block(
            sections, commit="a" * 40, digest="b" * 64
        )
        page = (
            "---\ntitle: x\n---\n\nIntro.\n\n"
            f"{generator.GENERATED_START}\nstale\n{generator.GENERATED_END}\n"
        )

        updated = generator.replace_generated_block(page, block)

        self.assertIn("Intro.\n\n" + generator.GENERATED_START, updated)
        self.assertNotIn("stale", updated)
        self.assertIn(
            f'source="canton-network/splice" path="{generator.SOURCE_PATH}" '
            f'ref="{"a" * 40}" digest="sha256:{"b" * 64}" common_metric_count="1"',
            updated,
        )
        self.assertEqual(
            [line for line in updated.splitlines() if line.startswith("## ")],
            [f"## {heading}" for _, heading in generator.SECTIONS],
        )

    def test_checked_in_page_carries_generated_block(self) -> None:
        page = generator.DEFAULT_OUTPUT.read_text(encoding="utf-8")
        self.assertEqual(page.count(generator.GENERATED_START), 1)
        self.assertEqual(page.count(generator.GENERATED_END), 1)
        for _, heading in generator.SECTIONS:
            self.assertIn(f"\n## {heading}\n", page)


if __name__ == "__main__":
    unittest.main()
