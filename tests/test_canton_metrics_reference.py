from __future__ import annotations

import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts import generate_canton_metrics_reference as generator


class CantonMetricsReferenceTests(unittest.TestCase):
    def test_resolve_generated_includes(self) -> None:
        with TemporaryDirectory() as tmp:
            generated_dir = Path(tmp)
            (generated_dir / "metrics.inc").write_text("daml.example\n^^^^^^^^^^^^", encoding="utf-8")

            resolved = generator.resolve_generated_includes(
                "Before\n.. generatedinclude:: metrics.inc\nAfter\n",
                generated_dir=generated_dir,
            )

        self.assertEqual(resolved, "Before\ndaml.example\n^^^^^^^^^^^^\nAfter\n")

    def test_convert_resolved_metrics_rst_to_mdx(self) -> None:
        rst = textwrap.dedent(
            """\
            .. _reference-metrics:

            Metrics
            -------

            For the metric types referenced below, see the `relevant Prometheus documentation <https://prometheus.io/docs/tutorials/understanding_metric_types/>`_.

            Participant Metrics
            ~~~~~~~~~~~~~~~~~~~

            daml.example.metric*
            ^^^^^^^^^^^^^^^^^^^^
            \t* **Summary**: Example summary with ``code``.
            \t* **Description**: The value for <operation>.
            \t* **Type**: meter
            \t* **Qualification**: Debug
            \t* **Labels**:
            \t\t* **sender**: The sequencer who sent the message
            """
        )

        mdx = generator.convert_rst_to_mdx(rst, source_ref="v1.2.3")

        self.assertIn('ref="v1.2.3"', mdx)
        self.assertIn("# Metrics", mdx)
        self.assertIn("[relevant Prometheus documentation](https://prometheus.io/docs/tutorials/understanding_metric_types/)", mdx)
        self.assertIn("### daml.example.metric\\*", mdx)
        self.assertIn("> - **Summary**: Example summary with `code`.", mdx)
        self.assertIn(r"> - **Description**: The value for \<operation\>.", mdx)
        self.assertIn(">   - **sender**: The sequencer who sent the message", mdx)

    def test_unresolved_generatedinclude_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "generatedinclude"):
            generator.convert_rst_to_mdx(".. generatedinclude:: metrics.inc\n", source_ref="v1.2.3")


if __name__ == "__main__":
    unittest.main()
