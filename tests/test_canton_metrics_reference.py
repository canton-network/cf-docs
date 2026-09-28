from __future__ import annotations

import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts import generate_canton_metrics_reference as generator


# Abridged copy of nix/tools/dpm/default.nix from Canton v3.5.19.
CANTON_TEMP_REGISTRY_DPM_NIX = textwrap.dedent(
    """\
    { pkgs ? import <nixpkgs> {} }:

    let
      dpmPath = "ghcr.io/digital-asset/temp/components/dpm";
      dpmVersion = "1.0.20";
      dpmRef = "${dpmPath}:${dpmVersion}";
    in
    pkgs.stdenv.mkDerivation {
      pname = "dpm";
      version = dpmVersion;
      src = pkgs.stdenv.mkDerivation {
        name = "dpm-pull-${dpmRef}";
        buildCommand = "oras pull -o $out ${dpmRef}";
      };
    }
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

    def test_repoint_canton_dpm_source_fetches_pinned_version_from_github_release(self) -> None:
        with TemporaryDirectory() as tmp:
            canton_dir = Path(tmp)
            nix_file = canton_dir / generator.CANTON_DPM_TOOL_NIX
            nix_file.parent.mkdir(parents=True)
            nix_file.write_text(CANTON_TEMP_REGISTRY_DPM_NIX, encoding="utf-8")

            repointed = generator.repoint_canton_dpm_source(canton_dir)
            rewritten = nix_file.read_text(encoding="utf-8")

        self.assertEqual(repointed, "1.0.20")
        self.assertNotIn(generator.CANTON_TEMP_DPM_REGISTRY, rewritten)
        self.assertIn('dpmVersion = "1.0.20";', rewritten)
        self.assertIn(
            "https://github.com/digital-asset/dpm/releases/download/${dpmVersion}/dpm-${dpmVersion}-${releasePlatform}.tar.gz",
            rewritten,
        )
        self.assertIn('"x86_64-linux" = "linux-amd64";', rewritten)
        self.assertIn(f'"x86_64-linux" = "{generator.DPM_RELEASE_HASHES["1.0.20"]["x86_64-linux"]}";', rewritten)
        self.assertIn("install -Dm755 dpm $out/bin/dpm", rewritten)

    def test_repoint_canton_dpm_source_leaves_github_release_definitions_alone(self) -> None:
        original = textwrap.dedent(
            """\
            { pkgs ? import <nixpkgs> {} }:
            let
              dpmVersion = "1.0.22";
            in
            pkgs.stdenv.mkDerivation {
              name = "dpm-gh";
              src = builtins.fetchurl {
                url = "https://github.com/digital-asset/dpm/releases/download/${dpmVersion}/dpm-${dpmVersion}-linux-amd64.tar.gz";
                sha256 = "sha256:1zw8w0vgjfz1m2fpk22dchvdavss38i9n7ycyjab1r325q3v5zgb";
              };
            }
            """
        )
        with TemporaryDirectory() as tmp:
            canton_dir = Path(tmp)
            nix_file = canton_dir / generator.CANTON_DPM_TOOL_NIX
            nix_file.parent.mkdir(parents=True)
            nix_file.write_text(original, encoding="utf-8")

            repointed = generator.repoint_canton_dpm_source(canton_dir)
            unchanged = nix_file.read_text(encoding="utf-8")

        self.assertIsNone(repointed)
        self.assertEqual(unchanged, original)

    def test_repoint_canton_dpm_source_skips_checkouts_without_dpm_tool(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertIsNone(generator.repoint_canton_dpm_source(Path(tmp)))

    def test_repoint_canton_dpm_source_rejects_unrecorded_versions(self) -> None:
        with TemporaryDirectory() as tmp:
            canton_dir = Path(tmp)
            nix_file = canton_dir / generator.CANTON_DPM_TOOL_NIX
            nix_file.parent.mkdir(parents=True)
            nix_file.write_text(CANTON_TEMP_REGISTRY_DPM_NIX.replace("1.0.20", "9.9.9"), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"dpm 9\.9\.9"):
                generator.repoint_canton_dpm_source(canton_dir)

    def test_dpm_release_hashes_cover_every_platform(self) -> None:
        for version, hashes in generator.DPM_RELEASE_HASHES.items():
            with self.subTest(version=version):
                self.assertEqual(set(hashes), set(generator.DPM_RELEASE_PLATFORMS))
                for digest in hashes.values():
                    self.assertRegex(digest, r"^sha256-[A-Za-z0-9+/]{43}=$")


if __name__ == "__main__":
    unittest.main()
