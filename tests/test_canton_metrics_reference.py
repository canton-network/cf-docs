from __future__ import annotations

import sys
import textwrap
import unittest
from pathlib import Path
from unittest import mock
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts import generate_canton_metrics_reference as generator


# Abridged Canton nix/tools/dpm/default.nix that fetches dpm from its GitHub release.
CANTON_GITHUB_RELEASE_DPM_NIX = textwrap.dedent(
    """\
    { pkgs ? import <nixpkgs> {} }:
    let
      dpmVersion = "1.0.20";
    in
    pkgs.stdenv.mkDerivation {
      name = "dpm-gh";
      src = builtins.fetchurl {
        url = "https://github.com/digital-asset/dpm/releases/download/${dpmVersion}/dpm-${dpmVersion}-linux-amd64.tar.gz";
        sha256 = "sha256-2TzC06qaJvOmvY3FcowNrz5Z7ktp7sVPeh4tt9h36q4=";
      };
    }
    """
)

# The dpm-1.0.20-checksums.txt asset published with the digital-asset/dpm 1.0.20 release.
DPM_1_0_20_CHECKSUMS = textwrap.dedent(
    """\
    860d08dc89841af3a870880cb9133757ffb1a1c0bde1ee5f44adb29a0d032553  dpm-1.0.20-darwin-amd64.tar.gz
    95a9f663f1d2cf168c74c5dc418d271ba6744fe46ee840894cbc9cfec2474a7f  dpm-1.0.20-darwin-arm64.tar.gz
    d93cc2d3aa9a26f3a6bd8dc5728c0daf3e59ee4b69eec54f7a1e2db7d877eaae  dpm-1.0.20-linux-amd64.tar.gz
    7a5ea81903e40f668e4c26925556cd84ee1c7692720fe5b7454681fa3a512c44  dpm-1.0.20-linux-arm64.tar.gz
    1db62e2c71becf76bbb5aa3aac9dd818f83eba22f9c619e6e996f6363e0f384a  dpm-1.0.20-windows-amd64.tar.gz
    """
)


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

    def write_dpm_tool(self, canton_dir: Path, source: str) -> Path:
        nix_file = canton_dir / generator.CANTON_DPM_TOOL_NIX
        nix_file.parent.mkdir(parents=True)
        nix_file.write_text(source, encoding="utf-8")
        return nix_file

    def test_dpm_release_hashes_convert_published_checksums_to_sri(self) -> None:
        hashes = generator.dpm_release_hashes(DPM_1_0_20_CHECKSUMS, "1.0.20")

        self.assertEqual(
            hashes,
            {
                "x86_64-linux": "sha256-2TzC06qaJvOmvY3FcowNrz5Z7ktp7sVPeh4tt9h36q4=",
                "aarch64-linux": "sha256-el6oGQPkD2aOTCaSVVbNhO4cdpJyD+W3RUaB+jpRLEQ=",
                "x86_64-darwin": "sha256-hg0I3ImEGvOocIgMuRM3V/+xocC94e5fRK2ymg0DJVM=",
                "aarch64-darwin": "sha256-lan2Y/HSzxaMdMXcQY0nG6Z0T+Ru6ECJTLyc/sJHSn8=",
            },
        )

    def test_dpm_release_hashes_reject_missing_platform(self) -> None:
        checksums = "\n".join(
            line for line in DPM_1_0_20_CHECKSUMS.splitlines() if "linux-arm64" not in line
        )

        with self.assertRaisesRegex(ValueError, "dpm-1.0.20-linux-arm64.tar.gz"):
            generator.dpm_release_hashes(checksums, "1.0.20")

    def test_repoint_rewrites_github_release_definition(self) -> None:
        with TemporaryDirectory() as tmp:
            canton_dir = Path(tmp)
            nix_file = self.write_dpm_tool(canton_dir, CANTON_GITHUB_RELEASE_DPM_NIX)

            with mock.patch.object(generator, "fetch_dpm_checksums", return_value=DPM_1_0_20_CHECKSUMS) as fetch:
                repointed = generator.repoint_canton_dpm_source(canton_dir)
            rewritten = nix_file.read_text(encoding="utf-8")

        fetch.assert_called_once_with("1.0.20")
        self.assertEqual(repointed, "1.0.20")
        self.assertIn('dpmVersion = "1.0.20";', rewritten)
        self.assertIn(
            "https://github.com/digital-asset/dpm/releases/download/${dpmVersion}/dpm-${dpmVersion}-${releasePlatform}.tar.gz",
            rewritten,
        )
        self.assertIn('"x86_64-linux" = "linux-amd64";', rewritten)
        self.assertIn('"x86_64-linux" = "sha256-2TzC06qaJvOmvY3FcowNrz5Z7ktp7sVPeh4tt9h36q4=";', rewritten)
        self.assertIn("install -Dm755 dpm $out/bin/dpm", rewritten)
        self.assertNotIn("builtins.fetchurl", rewritten)

    def test_repoint_skips_checkouts_without_dpm_tool(self) -> None:
        with TemporaryDirectory() as tmp:
            with mock.patch.object(generator, "fetch_dpm_checksums") as fetch:
                self.assertIsNone(generator.repoint_canton_dpm_source(Path(tmp)))

        fetch.assert_not_called()

    def test_repoint_rejects_definition_without_pinned_version(self) -> None:
        with TemporaryDirectory() as tmp:
            canton_dir = Path(tmp)
            self.write_dpm_tool(canton_dir, "{ pkgs ? import <nixpkgs> {} }: pkgs.dpm\n")

            with self.assertRaisesRegex(ValueError, "dpmVersion"):
                generator.repoint_canton_dpm_source(canton_dir)

if __name__ == "__main__":
    unittest.main()
