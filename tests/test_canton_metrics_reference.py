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
    def test_defaults_use_public_canton_source(self) -> None:
        self.assertEqual(generator.DEFAULT_RELEASE_REPO, "digital-asset/canton")
        self.assertEqual(generator.DEFAULT_REMOTE, "https://github.com/digital-asset/canton.git")

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

        self.assertIn('source="digital-asset/canton"', mdx)
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

    def test_run_generation_unsets_ci_for_canton_docs_generator(self) -> None:
        with TemporaryDirectory() as tmp:
            canton_dir = Path(tmp)
            (canton_dir / ".envrc").write_text("use nix\n", encoding="utf-8")
            calls: list[tuple[list[str], Path | None]] = []
            original_run = generator.run
            original_which = generator.shutil.which
            try:
                generator.run = lambda command, cwd=None, capture=False: calls.append((command, cwd)) or ""
                generator.shutil.which = lambda name: "/usr/bin/direnv" if name == "direnv" else None

                generator.run_generation(
                    canton_dir=canton_dir,
                    command=["sbt", "docs-open / generateIncludes"],
                    skip_direnv=False,
                )
            finally:
                generator.run = original_run
                generator.shutil.which = original_which

        self.assertEqual(
            calls,
            [
                (["direnv", "allow"], canton_dir),
                (
                    ["direnv", "exec", str(canton_dir), "env", "-u", "CI", "sbt", "docs-open / generateIncludes"],
                    canton_dir,
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
