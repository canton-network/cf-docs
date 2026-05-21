from __future__ import annotations

import io
import json
import tempfile
import textwrap
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from x2mdx.cli import main as cli_main
from x2mdx.jvm_docs.lifecycle import (
    build_jvm_doc_lifecycle_report_from_sources,
    parse_java_type_page,
    parse_scala_type_page,
)
from x2mdx.jvm_docs.models import JvmDocArtifactLifecycle, JvmDocLifecycleReport, JvmDocSymbolLifecycle
from x2mdx.jvm_docs.render import build_pages
from x2mdx.render import render_page
from x2mdx.jvm_docs.snapshots import load_jvm_doc_sources


def write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(contents).lstrip(), encoding="utf-8")


class JvmDocsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _build_jar(self, relative_path: str, files: dict[str, str]) -> None:
        jar_path = self.root / relative_path
        jar_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(jar_path, "w") as archive:
            for member_path, contents in files.items():
                archive.writestr(member_path, textwrap.dedent(contents).lstrip())

    def _write_manifest(self) -> Path:
        write_text(
            self.root / "status" / "bindings-java.yaml",
            """
            types:
              com.example.Foo:
                status: stable
              com.example.Foo.Inner:
                status: beta
              com.example.Legacy:
                status: stable
            """,
        )
        write_text(
            self.root / "status" / "bindings-scala.yaml",
            """
            types:
              com.example.scala.Baz:
                status: alpha
              com.example.scala.Qux:
                status: stable
            """,
        )
        self._build_jar(
            "jars/bindings-java/1.0.0/bindings-java-1.0.0-javadoc.jar",
            {
                "type-search-index.js": """
                    typeSearchIndex = [
                      {"p":"com.example","l":"Foo"},
                      {"p":"com.example","l":"Legacy"}
                    ];updateSearchResults();
                """,
                "member-search-index.js": """
                    memberSearchIndex = [{"p":"com.example","c":"Foo","l":"oldMethod","u":"oldMethod()"}];updateSearchResults();
                """,
                "com/example/Foo.html": """
                    <html>
                      <head><meta name="description" content="Foo summary v1.0.0"></head>
                      <body>
                        <div class="type-signature">public class Foo</div>
                        <section class="class-description"><div class="block">Foo summary v1.0.0</div></section>
                      </body>
                    </html>
                """,
                "com/example/Legacy.html": """
                    <html>
                      <head><meta name="description" content="Legacy summary v1.0.0"></head>
                      <body>
                        <div class="type-signature">public class Legacy</div>
                        <section class="class-description"><div class="block">Legacy summary v1.0.0</div></section>
                      </body>
                    </html>
                """,
            },
        )
        self._build_jar(
            "jars/bindings-java/1.1.0/bindings-java-1.1.0-javadoc.jar",
            {
                "type-search-index.js": """
                    typeSearchIndex = [
                      {"p":"com.example","l":"Foo"},
                      {"p":"com.example","l":"Foo.Inner"}
                    ];updateSearchResults();
                """,
                "member-search-index.js": """
                    memberSearchIndex = [
                      {"p":"com.example","c":"Foo","l":"oldMethod","u":"oldMethod()"},
                      {"p":"com.example","c":"Foo","l":"newMethod","u":"newMethod()"}
                    ];updateSearchResults();
                """,
                "deprecated-list.html": """
                    <div class="col-summary-item-name"><a href="com/example/Foo.html#oldMethod()">oldMethod</a></div>
                    <div class="col-last"><div class="deprecation-comment">Deprecated, since 1.1.0 use newMethod()</div></div>
                """,
                "com/example/Foo.html": """
                    <html>
                      <head><meta name="description" content="Foo summary v1.1.0"></head>
                      <body>
                        <div class="type-signature">public class Foo</div>
                        <section class="class-description"><div class="block">Foo summary v1.1.0</div></section>
                      </body>
                    </html>
                """,
                "com/example/Foo.Inner.html": """
                    <html>
                      <head><meta name="description" content="Foo.Inner summary v1.1.0"></head>
                      <body>
                        <div class="type-signature">public static final class Foo.Inner</div>
                        <section class="class-description"><div class="block">Foo.Inner summary v1.1.0</div></section>
                      </body>
                    </html>
                """,
            },
        )
        self._build_jar(
            "jars/bindings-java/1.2.0/bindings-java-1.2.0-javadoc.jar",
            {
                "type-search-index.js": """
                    typeSearchIndex = [
                      {"p":"com.example","l":"Foo"},
                      {"p":"com.example","l":"Foo.Inner"},
                      {"p":"com.example","l":"Bar"}
                    ];updateSearchResults();
                """,
                "member-search-index.js": """
                    memberSearchIndex = [{"p":"com.example","c":"Foo","l":"newMethod","u":"newMethod()"}];updateSearchResults();
                """,
                "deprecated-list.html": """
                    <div class="col-summary-item-name"><a href="com/example/Bar.html">Bar</a></div>
                    <div class="col-last"><div class="deprecation-comment">Deprecated, use Foo.Inner instead.</div></div>
                """,
                "com/example/Foo.html": """
                    <html>
                      <head><meta name="description" content="Foo summary v1.2.0"></head>
                      <body>
                        <div class="type-signature">public class Foo</div>
                        <section class="class-description"><div class="block">Foo summary v1.2.0</div></section>
                      </body>
                    </html>
                """,
                "com/example/Foo.Inner.html": """
                    <html>
                      <head><meta name="description" content="Foo.Inner summary v1.2.0"></head>
                      <body>
                        <div class="type-signature">public static final class Foo.Inner</div>
                        <section class="class-description"><div class="block">Foo.Inner summary v1.2.0</div></section>
                      </body>
                    </html>
                """,
                "com/example/Bar.html": """
                    <html>
                      <head><meta name="description" content="Bar summary v1.2.0"></head>
                      <body>
                        <div class="type-signature">public class Bar</div>
                        <section class="class-description"><div class="block">Bar summary v1.2.0</div></section>
                      </body>
                    </html>
                """,
            },
        )

        self._build_jar(
            "jars/bindings-scala_2.13/2.0.0/bindings-scala_2.13-2.0.0-javadoc.jar",
            {
                "index.js": """
                    Index.PACKAGES = {
                      "com.example.scala": [
                        {
                          "name": "com.example.scala.Baz",
                          "class": "com/example/scala/Baz.html",
                          "members_class": [
                            {"member":"com.example.scala.Baz.run","tail":"()","link":"com/example/scala/Baz.html#run()"}
                          ]
                        }
                      ]
                    };
                """,
                "com/example/scala/Baz.html": """
                    <html>
                      <head><meta content="Baz summary v2.0.0" name="description"></head>
                      <body>
                        <h4 id="signature" class="signature">final class Baz</h4>
                        <div id="comment" class="fullcommenttop"><div class="comment cmt"><p>Baz summary v2.0.0</p></div></div>
                      </body>
                    </html>
                """,
            },
        )
        self._build_jar(
            "jars/bindings-scala_2.13/2.1.0/bindings-scala_2.13-2.1.0-javadoc.jar",
            {
                "index.js": """
                    Index.PACKAGES = {
                      "com.example.scala": [
                        {
                          "name": "com.example.scala.Baz",
                          "class": "com/example/scala/Baz.html",
                          "members_class": [
                            {"member":"com.example.scala.Baz.run","tail":"()","link":"com/example/scala/Baz.html#run()"},
                            {"member":"com.example.scala.Baz.stop","tail":"()","link":"com/example/scala/Baz.html#stop()"}
                          ]
                        },
                        {
                          "name": "com.example.scala.Qux",
                          "class": "com/example/scala/Qux.html",
                          "members_class": []
                        }
                      ]
                    };
                """,
                "com/example/scala/Baz.html": """
                    <html>
                      <head><meta content="Baz summary v2.1.0" name="description"></head>
                      <body>
                        <h4 id="signature" class="signature">final class Baz</h4>
                        <div id="comment" class="fullcommenttop"><div class="comment cmt"><p>Baz summary v2.1.0</p></div></div>
                      </body>
                    </html>
                """,
                "com/example/scala/Qux.html": """
                    <html>
                      <head><meta content="Qux summary v2.1.0" name="description"></head>
                      <body>
                        <h4 id="signature" class="signature">final class Qux</h4>
                        <div id="comment" class="fullcommenttop"><div class="comment cmt"><p>Qux summary v2.1.0</p></div></div>
                      </body>
                    </html>
                """,
            },
        )

        manifest = {
            "source": "unit test jvm docs",
            "artifacts": [
                {
                    "group": "com.example",
                    "artifact": "bindings-java",
                    "language": "java",
                    "include_prefixes": ["com.example"],
                    "status_manifest": "status/bindings-java.yaml",
                    "versions": [
                        {"version": "1.0.0", "jar_path": "jars/bindings-java/1.0.0/bindings-java-1.0.0-javadoc.jar"},
                        {"version": "1.1.0", "jar_path": "jars/bindings-java/1.1.0/bindings-java-1.1.0-javadoc.jar"},
                        {"version": "1.2.0", "jar_path": "jars/bindings-java/1.2.0/bindings-java-1.2.0-javadoc.jar"},
                    ],
                },
                {
                    "group": "com.example",
                    "artifact": "bindings-scala_2.13",
                    "language": "scala",
                    "include_prefixes": ["com.example.scala"],
                    "status_manifest": "status/bindings-scala.yaml",
                    "versions": [
                        {"version": "2.0.0", "jar_path": "jars/bindings-scala_2.13/2.0.0/bindings-scala_2.13-2.0.0-javadoc.jar"},
                        {"version": "2.1.0", "jar_path": "jars/bindings-scala_2.13/2.1.0/bindings-scala_2.13-2.1.0-javadoc.jar"},
                    ],
                },
            ],
        }
        manifest_path = self.root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest_path

    def test_build_report_tracks_lifecycle_from_local_jars(self) -> None:
        manifest_path = self._write_manifest()
        sources = load_jvm_doc_sources(manifest_path)
        report = build_jvm_doc_lifecycle_report_from_sources(
            sources,
            source_name="unit test jars",
            version_filter="unit test versions",
        )

        self.assertEqual(report.summary["artifact_count"], 2)
        java_artifact = next(artifact for artifact in report.artifacts if artifact.artifact == "bindings-java")
        scala_artifact = next(artifact for artifact in report.artifacts if artifact.artifact == "bindings-scala_2.13")

        java_symbols = {symbol.symbol: symbol for symbol in java_artifact.symbols}
        self.assertEqual(java_symbols["com.example.Foo"].status, "stable")
        self.assertEqual(java_symbols["com.example.Foo"].latest_summary, "Foo summary v1.2.0")
        self.assertEqual(java_symbols["com.example.Foo.Inner"].status, "beta")
        self.assertEqual(java_symbols["com.example.Foo.Inner"].latest_summary, "Foo.Inner summary v1.2.0")
        self.assertEqual(java_symbols["com.example.Bar"].introduced_version, "1.2.0")
        self.assertEqual(java_symbols["com.example.Bar"].status, "deprecated")
        self.assertEqual(java_symbols["com.example.Foo#newMethod"].introduced_version, "1.1.0")
        self.assertEqual(java_symbols["com.example.Legacy"].latest_summary, "Legacy summary v1.0.0")
        self.assertEqual(java_symbols["com.example.Legacy"].removed_version, "1.1.0")

        old_method = java_symbols["com.example.Foo#oldMethod"]
        self.assertEqual(old_method.deprecated_version, "1.1.0")
        self.assertEqual(old_method.removed_version, "1.2.0")
        self.assertIn("newMethod", old_method.deprecation_note or "")

        scala_symbols = {symbol.symbol: symbol for symbol in scala_artifact.symbols}
        self.assertEqual(scala_symbols["com.example.scala.Baz"].status, "alpha")
        self.assertEqual(scala_symbols["com.example.scala.Baz"].latest_signature, "final class Baz")
        self.assertEqual(scala_symbols["com.example.scala.Baz"].latest_summary, "Baz summary v2.1.0")
        self.assertEqual(scala_symbols["com.example.scala.Qux"].status, "stable")
        self.assertEqual(scala_symbols["com.example.scala.Qux"].introduced_version, "2.1.0")
        self.assertEqual(scala_symbols["com.example.scala.Baz.stop()"].introduced_version, "2.1.0")

    def test_build_report_requires_status_for_non_deprecated_types(self) -> None:
        manifest_path = self._write_manifest()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"][0]["status_manifest"] = "status/missing-foo.yaml"
        write_text(
            self.root / "status" / "missing-foo.yaml",
            """
            types:
              com.example.Foo.Inner:
                status: beta
              com.example.Legacy:
                status: stable
            """,
        )
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        sources = load_jvm_doc_sources(manifest_path)
        with self.assertRaisesRegex(ValueError, r"Missing status for JVM doc type com\.example\.Foo"):
            build_jvm_doc_lifecycle_report_from_sources(
                sources,
                source_name="unit test jars",
                version_filter="unit test versions",
            )

    def test_render_escapes_mdx_sensitive_summary_text_and_encodes_doc_links(self) -> None:
        report = JvmDocLifecycleReport(
            source_name="unit test jars",
            version_filter="unit test versions",
            summary={"artifact_count": 1, "type_count": 1, "member_count": 1},
            notes=[],
            artifacts=[
                JvmDocArtifactLifecycle(
                    group="com.example",
                    artifact="bindings-scala",
                    language="scala",
                    versions=["1.0.0"],
                    symbol_count=2,
                    type_count=1,
                    member_count=1,
                    failures=[],
                    symbols=[
                        JvmDocSymbolLifecycle(
                            symbol_key="type:com.example.scala.Sample",
                            language="scala",
                            kind="type",
                            symbol="com.example.scala.Sample",
                            introduced_version="1.0.0",
                            deprecated_version=None,
                            removed_version=None,
                            versions_present=["1.0.0"],
                            doc_links={
                                "1.0.0": "https://example.com/Sample$.html#make[A<:Foo](value:Bar{Baz})"
                            },
                            latest_doc_path="com/example/scala/Sample.html",
                            status="stable",
                            latest_signature="trait Sample extends AnyRef",
                            latest_summary="Contains {braces} and ${dollar}.",
                        ),
                        JvmDocSymbolLifecycle(
                            symbol_key="member:com.example.scala.Sample.make|[A<:Foo](value:Bar{Baz})",
                            language="scala",
                            kind="member",
                            symbol="com.example.scala.Sample.make",
                            introduced_version="1.0.0",
                            deprecated_version=None,
                            removed_version=None,
                            versions_present=["1.0.0"],
                            doc_links={
                                "1.0.0": "https://example.com/Sample$.html#make[A<:Foo](value:Bar{Baz})"
                            },
                            latest_doc_path="com/example/scala/Sample.html",
                        ),
                    ],
                )
            ],
        )

        _, pages = build_pages(
            report,
            overview_output=Path("reference/jvm-api/index.mdx"),
            details_dir=Path("reference/jvm-api/details"),
            overview_title="Custom JVM Docs",
        )

        package_page = next(page for page in pages if page.path.endswith("bindings-scala-packages/com-example-scala/index.mdx"))
        object_page = next(page for page in pages if page.path.endswith("bindings-scala-packages/com-example-scala/sample.mdx"))

        package_text = render_page(package_page)
        object_text = render_page(object_page)

        self.assertIn("Contains \\{braces\\} and \\$\\{dollar\\}.", package_text)
        self.assertIn(
            "[Open](<https://example.com/Sample%24.html#make%5BA%3C:Foo%5D%28value:Bar%7BBaz%7D%29>)",
            object_text,
        )

    def test_java_meta_description_fallback_ignores_declaration_text(self) -> None:
        _, summary = parse_java_type_page(
            """
            <html>
              <head>
                <meta name="description" content="declaration: package: com.example, class: Foo">
              </head>
              <body>
                <div class="type-signature">public class Foo</div>
              </body>
            </html>
            """
        )

        self.assertEqual(summary, "")

    def test_scala_meta_description_fallback_ignores_bare_symbol_text(self) -> None:
        _, summary = parse_scala_type_page(
            """
            <html>
              <head>
                <meta content="- com.example.scala.PrimitiveInstances" name="description">
              </head>
              <body>
                <h4 id="signature" class="signature">sealed abstract class PrimitiveInstances extends AnyRef</h4>
              </body>
            </html>
            """
        )

        self.assertEqual(summary, "")

    def test_cli_builds_pages_and_updates_docs_json(self) -> None:
        manifest_path = self._write_manifest()
        docs_json = self.root / "docs.json"
        docs_json.write_text(
            json.dumps(
                {
                    "navigation": {
                        "dropdowns": [
                            {"dropdown": "Reference", "pages": []},
                        ]
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        overview = self.root / "reference" / "jvm-api" / "index.mdx"
        details_dir = self.root / "reference" / "jvm-api" / "details"

        result = cli_main(
            [
                "jvm-docs",
                "build-api-pages-from-manifest",
                "--manifest",
                str(manifest_path),
                "--overview-file",
                str(overview),
                "--details-dir",
                str(details_dir),
                "--overview-title",
                "Custom JVM Docs",
                "--docs-json",
                str(docs_json),
                "--nav-dropdown",
                "Reference",
                "--source-name",
                "unit test jars",
                "--version-filter",
                "unit test versions",
            ]
        )

        self.assertEqual(result, 0)
        self.assertTrue(overview.exists())
        self.assertTrue((details_dir / "bindings-java.mdx").exists())
        self.assertTrue((details_dir / "bindings-scala-2-13.mdx").exists())
        java_package_dir = details_dir / "bindings-java-packages" / "com-example"
        scala_package_dir = details_dir / "bindings-scala-2-13-packages" / "com-example-scala"
        self.assertTrue((java_package_dir / "index.mdx").exists())
        self.assertTrue((scala_package_dir / "index.mdx").exists())
        self.assertTrue((java_package_dir / "foo.mdx").exists())
        self.assertTrue((java_package_dir / "foo-inner.mdx").exists())
        self.assertTrue((java_package_dir / "bar.mdx").exists())
        self.assertTrue((java_package_dir / "legacy.mdx").exists())

        overview_text = overview.read_text(encoding="utf-8")
        java_text = (details_dir / "bindings-java.mdx").read_text(encoding="utf-8")
        java_package_text = (java_package_dir / "index.mdx").read_text(encoding="utf-8")
        java_object_text = (java_package_dir / "foo.mdx").read_text(encoding="utf-8")
        nested_object_text = (java_package_dir / "foo-inner.mdx").read_text(encoding="utf-8")
        removed_object_text = (java_package_dir / "legacy.mdx").read_text(encoding="utf-8")
        deprecated_object_text = (java_package_dir / "bar.mdx").read_text(encoding="utf-8")
        docs_payload = json.loads(docs_json.read_text(encoding="utf-8"))

        self.assertIn("Custom JVM Docs", overview_text)
        self.assertIn("details/bindings-java", overview_text)
        self.assertIn("## Table of Contents", java_text)
        self.assertIn("| NAME | STATUS | SUMMARY |", java_text)
        self.assertIn("🟢 Active Since", java_text)
        self.assertIn("## Version Change Summary", java_text)
        self.assertIn("## Reference", java_text)
        self.assertIn("1.0.0", java_text)
        self.assertIn("1.1.0", java_text)
        self.assertIn("1.2.0", java_text)
        self.assertNotIn("## Artifact", java_text)
        self.assertNotIn("## Lifecycle Summary", java_text)
        self.assertNotIn("## Package Reference", java_text)
        self.assertIn("## Package `com.example`", java_package_text)
        self.assertIn("[`Foo`](./foo)", java_package_text)
        self.assertIn("[`Foo.Inner`](./foo-inner)", java_package_text)
        self.assertIn("[`Bar`](./bar)", java_package_text)
        self.assertIn("[`Legacy`](./legacy)", java_package_text)
        self.assertIn("## Table of Contents", java_package_text)
        self.assertIn("| NAME | STATUS | SUMMARY |", java_package_text)
        self.assertIn("`stable`", java_package_text)
        self.assertIn("`beta`", java_package_text)
        self.assertIn("`deprecated`", java_package_text)
        self.assertIn("Removed in 1.1.0.", java_package_text)
        self.assertNotIn("## Reference", java_package_text)
        self.assertNotIn("**Signature**", java_package_text)
        self.assertNotIn("**Members**", java_package_text)
        self.assertIn("title: \"Foo\"", java_object_text)
        self.assertIn("description: \"Foo summary v1.2.0\"", java_object_text)
        self.assertIn("## Foo - stable", java_object_text)
        self.assertIn("Upstream docs: [Open](", java_object_text)
        self.assertIn("**Signature**", java_object_text)
        self.assertIn("**Members**", java_object_text)
        self.assertNotIn("**Summary**", java_object_text)
        self.assertIn("`newMethod`", java_object_text)
        self.assertIn("title: \"Foo.Inner\"", nested_object_text)
        self.assertIn("## Foo.Inner - beta", nested_object_text)
        self.assertIn("title: \"Legacy\"", removed_object_text)
        self.assertIn("description: \"Legacy summary v1.0.0\"", removed_object_text)
        self.assertIn("## Legacy - stable", removed_object_text)
        self.assertIn("Removed in `1.1.0`.", removed_object_text)
        self.assertIn("title: \"Bar\"", deprecated_object_text)
        self.assertIn("## Bar - deprecated", deprecated_object_text)
        self.assertNotIn("### Signature", java_package_text)
        self.assertNotIn("### Summary", java_package_text)
        self.assertNotIn("### Members", java_package_text)
        self.assertNotIn("style=", java_package_text)
        self.assertNotIn("<span", java_package_text)
        self.assertEqual(
            docs_payload["navigation"]["dropdowns"][0]["pages"],
            ["reference/jvm-api/index"],
        )

    def test_cli_list_formats_outputs_all_supported_formats(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = cli_main(["list-formats"])

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "jvm-docs\ndaml-json\nprotobuf\ntypedoc\nasyncapi\nopenrpc\n")
