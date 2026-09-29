from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts import generate_canton_metrics_reference as generator  # noqa: E402


ASSET = generator.ReleaseAsset(
    tag="v1.2.3",
    version="1.2.3",
    name="canton-open-source-1.2.3.tar.gz",
    url="https://example.com/canton-open-source-1.2.3.tar.gz",
    size=1,
    digest="sha256:" + "a" * 64,
)


def metric(name: str, **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "name": name,
        "summary": f"Summary of {name}.",
        "description": f"Description of {name}.",
        "type": "counter",
        "qualification": "Debug",
        "labels": {},
    }
    item.update(overrides)
    return item


def payload(**sections: list[dict[str, object]]) -> dict[str, object]:
    metrics: dict[str, object] = {
        "participant": [metric("daml.participant.example")],
        "sequencer": [metric("daml.sequencer.example")],
        "mediator": [metric("daml.mediator.example")],
    }
    metrics.update(sections)
    return {"metrics": metrics}


class CantonMetricsReferenceTests(unittest.TestCase):
    def test_generation_runs_metrics_script_with_docs_flag(self) -> None:
        self.assertTrue(generator.REFERENCE_SCRIPT.is_file())
        self.assertEqual(
            generator.METRICS_DOCS_ENVIRONMENT, {"GENERATE_METRICS_FOR_DOCS": ""}
        )
        self.assertEqual(generator.DEFAULT_RELEASE_REPO, "digital-asset/canton")

    def test_render_metric_matches_canton_docs_formatting(self) -> None:
        item = generator.load_metric(
            metric(
                "daml.db.commit",
                summary="The time needed to perform the SQL query commit.",
                description=(
                    "This metric measures the time relating to the <operation>.\n"
                    "    It roughly corresponds to calling ``commit()`` on a {connection};\n"
                    "see `the guide <https://example.com/guide>`_."
                ),
                type="timer",
                labels={
                    "name": "The operation/pool for which the metric is registered."
                },
            ),
            node="participant",
        )

        self.assertEqual(
            generator.render_metric(item),
            [
                r"### daml.db.commit\*",
                "",
                "> - **Summary**: The time needed to perform the SQL query commit.",
                (
                    r"> - **Description**: This metric measures the time relating to the \<operation\>. "
                    r"It roughly corresponds to calling `commit()` on a \{connection\}; "
                    "see [the guide](https://example.com/guide)."
                ),
                "> - **Type**: timer",
                "> - **Qualification**: Debug",
                "> - **Labels**:",
                ">   - **name**: The operation/pool for which the metric is registered.",
            ],
        )

    def test_render_generated_block_sorts_deduplicates_and_records_provenance(
        self,
    ) -> None:
        metrics = generator.load_metrics(
            payload(
                participant=[
                    metric("daml.participant.zeta"),
                    metric("daml.participant.alpha"),
                    metric("daml.participant.zeta", summary="A repeated registration."),
                ]
            )
        )

        block = generator.render_generated_block(metrics, asset=ASSET)

        self.assertTrue(block.startswith(generator.GENERATED_START + "\n"))
        self.assertTrue(block.endswith("\n" + generator.GENERATED_END))
        self.assertIn(
            '{/* GENERATED_FROM source="digital-asset/canton" ref="v1.2.3" '
            'asset="canton-open-source-1.2.3.tar.gz" digest="sha256:' + "a" * 64 + '" '
            'participant_metric_count="2" sequencer_metric_count="1" mediator_metric_count="1" */}',
            block,
        )
        self.assertLess(
            block.index("## Participant Metrics"), block.index("## Sequencer Metrics")
        )
        self.assertLess(
            block.index("## Sequencer Metrics"), block.index("## Mediator Metrics")
        )
        self.assertLess(
            block.index("### daml.participant.alpha"),
            block.index("### daml.participant.zeta"),
        )
        self.assertEqual(block.count("### daml.participant.zeta"), 1)
        self.assertNotIn("A repeated registration.", block)

    def test_load_metrics_rejects_missing_or_empty_sections(self) -> None:
        with self.assertRaisesRegex(ValueError, "metrics object"):
            generator.load_metrics({"console": []})
        with self.assertRaisesRegex(ValueError, "no mediator metrics"):
            generator.load_metrics(payload(mediator=[]))

    def test_load_metrics_rejects_malformed_items(self) -> None:
        with self.assertRaisesRegex(ValueError, "'summary'"):
            generator.load_metrics(
                payload(sequencer=[metric("daml.sequencer.example", summary=None)])
            )
        with self.assertRaisesRegex(ValueError, "malformed labels"):
            generator.load_metrics(
                payload(sequencer=[metric("daml.sequencer.example", labels={"x": 1})])
            )

    def test_replace_generated_block_keeps_authored_sections(self) -> None:
        page = "\n".join(
            [
                "# Metrics",
                "",
                "Intro.",
                "",
                generator.GENERATED_START,
                "",
                "old generated content",
                "",
                generator.GENERATED_END,
                "",
                "## Health Metrics",
                "",
                "Authored content.",
                "",
            ]
        )
        block = f"{generator.GENERATED_START}\n\nnew generated content\n\n{generator.GENERATED_END}"

        updated = generator.replace_generated_block(page, block)

        self.assertEqual(
            updated,
            f"# Metrics\n\nIntro.\n\n{block}\n\n## Health Metrics\n\nAuthored content.\n",
        )

    def test_replace_generated_block_requires_markers(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing its"):
            generator.replace_generated_block("# Metrics\n", "block")

    def test_committed_page_has_generated_block_markers(self) -> None:
        page = generator.DEFAULT_OUTPUT.read_text(encoding="utf-8")

        self.assertEqual(page.count(generator.GENERATED_START), 1)
        self.assertEqual(page.count(generator.GENERATED_END), 1)
        self.assertLess(
            page.index(generator.GENERATED_END), page.index("## Health Metrics")
        )


if __name__ == "__main__":
    unittest.main()
