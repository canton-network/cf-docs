"""Compile real Java/Scala examples, then verify extracted states and rendered MDX.

Run with JAVADOC, JAVAC and SCALADOC pointing at the desired toolchain.
JVM_EXAMPLE_OUTPUT preserves the generated archives and pages for inspection.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from x2mdx.cli import main
from x2mdx.jvm_docs.annotations import doc_annotations
from x2mdx.jvm_docs.lifecycle import (
    build_jvm_doc_lifecycle_report_from_sources,
    consolidate_lifecycle,
)
from x2mdx.jvm_docs.models import JvmDocArtifactSource, JvmDocVersionSource
from x2mdx.jvm_docs.snapshots import load_jvm_doc_sources

FIXTURE = Path(__file__).parent / "fixtures" / "jvm-lifecycle"


def tool(name: str) -> str:
    candidate = os.environ.get(name.upper(), name)
    resolved = shutil.which(candidate)
    if not resolved:
        raise unittest.SkipTest(f"{name} required for real JVM annotation examples")
    return resolved


def build_examples(root: Path) -> Path:
    javac, javadoc, scaladoc = (tool(name) for name in ("javac", "javadoc", "scaladoc"))
    classes = root / "classes"
    classes.mkdir(parents=True, exist_ok=True)
    annotations = sorted(map(str, (FIXTURE / "annotations").rglob("*.java")))
    subprocess.run(
        [javac, "-d", str(classes), *annotations],
        check=True,
        capture_output=True,
        text=True,
    )
    artifacts = []
    for language in ("java", "scala"):
        docs = root / f"{language}-docs"
        docs.mkdir(parents=True, exist_ok=True)
        if language == "java":
            sources = sorted(map(str, (FIXTURE / language).rglob("*.java")))
            command = [
                javadoc,
                "-quiet",
                "-Xdoclint:none",
                "-classpath",
                str(classes),
                "-d",
                str(docs),
                *sources,
            ]
        else:
            sources = sorted(map(str, (FIXTURE / language).rglob("*.scala")))
            command = [scaladoc, "-classpath", str(classes), "-d", str(docs), *sources]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        (root / f"{language}-compiler.log").write_text(result.stdout + result.stderr)
        jar = root / f"{language}-docs.jar"
        with zipfile.ZipFile(jar, "w") as archive:
            for path in sorted(docs.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(docs))
        artifacts.append(
            {
                "group": "example",
                "artifact": f"example-{language}",
                "language": language,
                "include_prefixes": ["example.api"],
                "versions": [{"version": "1.0.0", "jar_path": jar.name}],
            }
        )
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"artifacts": artifacts}, indent=2))
    return manifest


class JvmAnnotationTests(unittest.TestCase):
    def test_declaration_scope_and_conflicts(self):
        source = """<div class="type-signature"><span class="annotations">@other.Alpha</span> class Example</div>
        <p>@Beta in prose</p><section class="detail" id="method()"><div class="member-signature">
        <span class="annotations">@Description("@Stable") @Beta</span> void method()</div></section>"""
        self.assertEqual(
            doc_annotations(source, language="java"),
            {"": ("alpha", None), "method()": ("beta", None)},
        )
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            doc_annotations(
                '<div class="type-signature"><span class="annotations">@Alpha @Beta</span></div>',
                language="java",
            )

    def test_latest_snapshot_clears_earlier_marker(self):
        source = JvmDocArtifactSource(
            "example",
            "api",
            "java",
            versions=[
                JvmDocVersionSource("1.0.0", "unused"),
                JvmDocVersionSource("1.1.0", "unused"),
            ],
        )
        record = {
            "symbol_key": "api:java:type:Example",
            "kind": "type",
            "language": "java",
            "symbol": "Example",
            "doc_url": "https://example.com/Example.html",
            "doc_path": "Example.html",
        }
        for state in ("beta", "stable", None):
            with self.subTest(state=state):
                result = consolidate_lifecycle(
                    source,
                    {
                        "1.0.0": [dict(record, lifecycle_state="alpha")],
                        "1.1.0": [dict(record, lifecycle_state=state)],
                    },
                )
                self.assertEqual(result[0].lifecycle_state, state)

    def test_real_java_and_scala_annotations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(os.environ.get("JVM_EXAMPLE_OUTPUT", temp)).resolve()
            root.mkdir(parents=True, exist_ok=True)
            manifest = build_examples(root)
            report = build_jvm_doc_lifecycle_report_from_sources(
                load_jvm_doc_sources(manifest),
                source_name="source annotations",
                version_filter="1.0.0",
            )
            for artifact in report.artifacts:
                with self.subTest(language=artifact.language):
                    self.assertEqual(artifact.failures, [])
                    types = {
                        s.symbol.rsplit(".", 1)[-1]: s
                        for s in artifact.symbols
                        if s.kind == "type"
                    }
                    for name, state in {
                        "Example": "alpha",
                        "Preview": "beta",
                        "Released": "stable",
                        "Unmarked": None,
                    }.items():
                        self.assertEqual(types[name].lifecycle_state, state)
                        self.assertIsNone(types[name].deprecated_version)
                    self.assertEqual(types["Legacy"].deprecated_version, "1.0.0")
                    members = [s for s in artifact.symbols if s.kind == "member"]
                    for name, state in {
                        "preview": "beta",
                        "released": "stable",
                        "unmarked": None,
                    }.items():
                        member = next(s for s in members if f"{name}(" in s.symbol)
                        self.assertEqual(member.lifecycle_state, state)
                        self.assertIsNone(member.deprecated_version)
                    self.assertEqual(
                        next(
                            s for s in members if "legacy(" in s.symbol
                        ).deprecated_version,
                        "1.0.0",
                    )
            for language in ("java", "scala"):
                payload = json.loads(manifest.read_text())
                payload["artifacts"] = [
                    a for a in payload["artifacts"] if a["language"] == language
                ]
                language_manifest = root / f"{language}-manifest.json"
                language_manifest.write_text(json.dumps(payload))
                site = root / "site" / language
                self.assertEqual(
                    main(
                        [
                            "jvm-docs",
                            "build-api-pages-from-manifest",
                            "--manifest",
                            str(language_manifest),
                            "--overview-file",
                            str(site / "index.mdx"),
                            "--details-dir",
                            str(site / "details"),
                            "--history-report",
                            str(root / f"{language}-history.json"),
                            "--reader-route-prefix",
                            f"jvm-examples/{language}",
                            "--surface-id",
                            f"{language}-examples",
                            "--surface-title",
                            f"{language.title()} annotation examples",
                        ]
                    ),
                    0,
                )
                package = (
                    site / "details" / f"example-{language}-packages" / "example-api"
                )
                example = (package / "example.mdx").read_text()
                self.assertIn(">Alpha</span>", example)
                self.assertIn("Beta", example)
                self.assertIn("Deprecated `1.0.0`", example)
                self.assertIn(f"```{language}", example)
                self.assertIn(">Beta</span>", (package / "preview.mdx").read_text())
                self.assertNotIn(
                    ">Stable</span>", (package / "released.mdx").read_text()
                )
                self.assertIn("Deprecated", (package / "legacy.mdx").read_text())
                self.assertNotIn(
                    ">Alpha</span>", (package / "unmarked.mdx").read_text()
                )

                legacy_site = root / "legacy-site" / language
                self.assertEqual(
                    main(
                        [
                            "jvm-docs",
                            "build-api-pages-from-manifest",
                            "--manifest",
                            str(language_manifest),
                            "--overview-file",
                            str(legacy_site / "index.mdx"),
                            "--details-dir",
                            str(legacy_site / "details"),
                        ]
                    ),
                    0,
                )
                legacy_example = (
                    legacy_site
                    / "details"
                    / f"example-{language}-packages"
                    / "example-api"
                    / "example.mdx"
                ).read_text()
                self.assertIn("Example - alpha", legacy_example)
                self.assertIn("· Beta", legacy_example)


if __name__ == "__main__":
    unittest.main()
