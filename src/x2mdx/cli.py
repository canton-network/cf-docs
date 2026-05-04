"""CLI for x2mdx."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import shutil


def build_jvm_doc_report_from_manifest_args(args: argparse.Namespace):
    from x2mdx.jvm_docs.lifecycle import build_jvm_doc_lifecycle_report_from_sources
    from x2mdx.jvm_docs.snapshots import load_jvm_doc_sources

    manifest_path = Path(args.manifest)
    include_versions = set(args.version) if args.version else None
    fixture_root = Path(args.fixture_root) if args.fixture_root else None
    sources = load_jvm_doc_sources(
        manifest_path,
        fixture_root=fixture_root,
        include_versions=include_versions,
    )
    return build_jvm_doc_lifecycle_report_from_sources(
        sources,
        source_name=args.source_name or str(manifest_path),
        version_filter=args.version_filter or ("selected manifest versions" if include_versions else "manifest versions"),
    )


def build_daml_doc_report_from_manifest_args(args: argparse.Namespace):
    from x2mdx.daml_json.lifecycle import build_daml_doc_report_from_sources
    from x2mdx.daml_json.snapshots import load_daml_doc_sources

    manifest_path = Path(args.manifest)
    include_versions = set(args.version) if args.version else None
    fixture_root = Path(args.fixture_root) if args.fixture_root else None
    sources = load_daml_doc_sources(
        manifest_path,
        fixture_root=fixture_root,
        include_versions=include_versions,
    )
    return build_daml_doc_report_from_sources(
        sources,
        source_name=args.source_name or sources.source or str(manifest_path),
        version_filter=args.version_filter or ("selected manifest versions" if include_versions else "manifest versions"),
        publish_version=args.publish_version,
    )


def build_protobuf_report_from_manifest_args(args: argparse.Namespace):
    from x2mdx.protobuf.lifecycle import build_protobuf_history_report_from_sources
    from x2mdx.protobuf.snapshots import load_protobuf_sources

    manifest_path = Path(args.manifest)
    include_versions = set(args.version) if args.version else None
    fixture_root = Path(args.fixture_root) if args.fixture_root else None
    sources = load_protobuf_sources(
        manifest_path,
        fixture_root=fixture_root,
        include_versions=include_versions,
    )
    return build_protobuf_history_report_from_sources(
        sources,
        source_name=args.source_name or sources.source or str(manifest_path),
        version_filter=args.version_filter or ("selected manifest versions" if include_versions else "manifest versions"),
    )


def build_typedoc_report_from_manifest_args(args: argparse.Namespace):
    from x2mdx.typedoc.lifecycle import build_typedoc_report_from_sources
    from x2mdx.typedoc.snapshots import load_typedoc_sources

    manifest_path = Path(args.manifest)
    include_versions = set(args.version) if args.version else None
    fixture_root = Path(args.fixture_root) if args.fixture_root else None
    sources = load_typedoc_sources(
        manifest_path,
        fixture_root=fixture_root,
        include_versions=include_versions,
    )
    return build_typedoc_report_from_sources(
        sources,
        source_name=args.source_name or sources.source or str(manifest_path),
        version_filter=args.version_filter or ("selected manifest versions" if include_versions else "manifest versions"),
        publish_version=args.publish_version,
    )


def build_asyncapi_report_from_manifest_args(args: argparse.Namespace):
    from x2mdx.asyncapi.lifecycle import build_asyncapi_report_from_sources
    from x2mdx.asyncapi.snapshots import load_asyncapi_source_snapshots

    manifest_path = Path(args.manifest)
    include_versions = set(args.version) if args.version else None
    fixture_root = Path(args.fixture_root) if args.fixture_root else None
    sources = load_asyncapi_source_snapshots(
        manifest_path,
        fixture_root=fixture_root,
        include_versions=include_versions,
    )
    return build_asyncapi_report_from_sources(
        sources,
        source_name=args.source_name or str(manifest_path),
        version_filter=args.version_filter or ("selected manifest versions" if include_versions else "manifest versions"),
        publish_version=args.publish_version,
    )


def build_openrpc_report_from_manifest_args(args: argparse.Namespace):
    from x2mdx.openrpc.lifecycle import build_openrpc_report_from_sources
    from x2mdx.openrpc.snapshots import load_openrpc_source_snapshots

    manifest_path = Path(args.manifest)
    include_versions = set(args.version) if args.version else None
    fixture_root = Path(args.fixture_root) if args.fixture_root else None
    sources = load_openrpc_source_snapshots(
        manifest_path,
        fixture_root=fixture_root,
        include_versions=include_versions,
    )
    return build_openrpc_report_from_sources(
        sources,
        source_name=args.source_name or str(manifest_path),
        version_filter=args.version_filter or ("selected manifest versions" if include_versions else "manifest versions"),
        publish_version=args.publish_version,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="x2mdx")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-formats", help="List supported input formats")

    jvm_docs = subparsers.add_parser("jvm-docs", help="Javadoc/Scaladoc commands")
    jvm_docs_subparsers = jvm_docs.add_subparsers(dest="jvm_docs_command", required=True)

    build_jvm_docs = jvm_docs_subparsers.add_parser(
        "build-api-pages-from-manifest",
        help="Build JVM API lifecycle pages directly from local Javadoc/Scaladoc jars",
    )
    build_jvm_docs.add_argument(
        "--manifest",
        required=True,
        help="Path to a JSON/YAML manifest that lists local Javadoc/Scaladoc jars",
    )
    build_jvm_docs.add_argument(
        "--overview-file",
        required=True,
        help="Exact MDX file path to write for the overview page",
    )
    build_jvm_docs.add_argument(
        "--details-dir",
        required=True,
        help="Directory where artifact and type pages should be written",
    )
    build_jvm_docs.add_argument(
        "--fixture-root",
        help="Directory to resolve manifest jar paths from; defaults to the manifest directory",
    )
    build_jvm_docs.add_argument(
        "--version",
        action="append",
        default=[],
        help="Version to include from the manifest. Repeat to include multiple versions.",
    )
    build_jvm_docs.add_argument(
        "--source-name",
        help="Optional source label to record in the lifecycle report",
    )
    build_jvm_docs.add_argument(
        "--version-filter",
        help="Optional label describing the selected version set",
    )
    build_jvm_docs.add_argument(
        "--overview-title",
        default="JVM API Lifecycle",
        help="Title to use for the generated overview page.",
    )
    build_jvm_docs.add_argument(
        "--docs-json",
        help="Optional docs.json file to update with the generated overview page",
    )
    build_jvm_docs.add_argument(
        "--nav-dropdown",
        help="Dropdown label in docs.json where the generated overview page should be inserted",
    )
    build_jvm_docs.add_argument(
        "--nav-version",
        action="append",
        default=[],
        help="Version label under the selected dropdown to update. Repeat to target multiple versions. Defaults to all versions in the dropdown.",
    )
    build_jvm_docs.add_argument(
        "--nav-group",
        action="append",
        default=[],
        help="Group label path under the selected dropdown/version where the page should be inserted. Repeat for nested groups.",
    )

    daml_json = subparsers.add_parser("daml-json", help="Daml docs JSON commands")
    daml_json_subparsers = daml_json.add_subparsers(dest="daml_json_command", required=True)

    build_daml_json = daml_json_subparsers.add_parser(
        "build-api-pages-from-manifest",
        help="Build Daml docs MDX pages directly from local docs JSON snapshots",
    )
    build_daml_json.add_argument(
        "--manifest",
        required=True,
        help="Path to a JSON/YAML manifest that lists local Daml docs JSON snapshots",
    )
    build_daml_json.add_argument(
        "--output-dir",
        required=True,
        help="Directory where generated MDX pages should be written",
    )
    build_daml_json.add_argument(
        "--fixture-root",
        help="Directory to resolve manifest JSON paths from; defaults to the manifest directory",
    )
    build_daml_json.add_argument(
        "--version",
        action="append",
        default=[],
        help="Version to include from the manifest. Repeat to include multiple versions.",
    )
    build_daml_json.add_argument(
        "--publish-version",
        help="Version whose module tree should be published; defaults to the manifest or latest selected version.",
    )
    build_daml_json.add_argument(
        "--source-name",
        help="Optional source label to record in the generated pages.",
    )
    build_daml_json.add_argument(
        "--version-filter",
        help="Optional label describing the selected version set.",
    )
    build_daml_json.add_argument(
        "--overview-title",
        default="Daml Standard Library",
        help="Title to use for the generated overview page.",
    )
    build_daml_json.add_argument(
        "--link-prefix",
        help="Optional root-relative URL prefix to use for overview-page module links.",
    )

    protobuf = subparsers.add_parser("protobuf", help="Descriptor-backed protobuf commands")
    protobuf_subparsers = protobuf.add_subparsers(dest="protobuf_command", required=True)

    build_protobuf = protobuf_subparsers.add_parser(
        "build-api-pages-from-manifest",
        help="Build protobuf history and package pages directly from local descriptor-image snapshots",
    )
    build_protobuf.add_argument(
        "--manifest",
        required=True,
        help="Path to a JSON/YAML manifest that lists local protobuf descriptor-image snapshots",
    )
    build_protobuf.add_argument(
        "--output-dir",
        required=True,
        help="Directory where generated MDX pages should be written",
    )
    build_protobuf.add_argument(
        "--fixture-root",
        help="Directory to resolve manifest paths from; defaults to the manifest directory",
    )
    build_protobuf.add_argument(
        "--version",
        action="append",
        default=[],
        help="Version to include from the manifest. Repeat to include multiple versions.",
    )
    build_protobuf.add_argument(
        "--source-name",
        help="Optional source label to record in the generated pages.",
    )
    build_protobuf.add_argument(
        "--version-filter",
        help="Optional label describing the selected version set.",
    )

    typedoc = subparsers.add_parser("typedoc", help="TypeDoc-based TypeScript bindings commands")
    typedoc_subparsers = typedoc.add_subparsers(dest="typedoc_command", required=True)

    build_typedoc = typedoc_subparsers.add_parser(
        "build-api-pages-from-manifest",
        help="Build TypeScript bindings MDX directly from local TypeDoc JSON snapshots",
    )
    build_typedoc.add_argument(
        "--manifest",
        required=True,
        help="Path to a JSON/YAML manifest that lists local TypeDoc JSON snapshots",
    )
    build_typedoc.add_argument(
        "--output-file",
        required=True,
        help="Exact MDX file path to write for the generated TypeScript bindings page",
    )
    build_typedoc.add_argument(
        "--fixture-root",
        help="Directory to resolve manifest JSON paths from; defaults to the manifest directory",
    )
    build_typedoc.add_argument(
        "--version",
        action="append",
        default=[],
        help="Version to include from the manifest. Repeat to include multiple versions.",
    )
    build_typedoc.add_argument(
        "--publish-version",
        help="Version whose bindings surface should be published; defaults to the manifest or latest selected version.",
    )
    build_typedoc.add_argument(
        "--source-name",
        help="Optional source label to record in the generated page.",
    )
    build_typedoc.add_argument(
        "--version-filter",
        help="Optional label describing the selected version set.",
    )
    build_typedoc.add_argument(
        "--page-title",
        default="TypeScript/JavaScript",
        help="Title to use for the generated page.",
    )
    build_typedoc.add_argument(
        "--page-description",
        default="TypeScript and JavaScript language bindings for Canton.",
        help="Description to use for the generated page.",
    )

    asyncapi = subparsers.add_parser("asyncapi", help="AsyncAPI websocket commands")
    asyncapi_subparsers = asyncapi.add_subparsers(dest="asyncapi_command", required=True)

    build_asyncapi = asyncapi_subparsers.add_parser(
        "build-api-pages-from-manifest",
        help="Build AsyncAPI MDX directly from local AsyncAPI snapshots",
    )
    build_asyncapi.add_argument(
        "--manifest",
        required=True,
        help="Path to a JSON/YAML manifest that lists local AsyncAPI snapshots",
    )
    build_asyncapi.add_argument(
        "--output-dir",
        help="Directory where generated MDX pages should be written",
    )
    build_asyncapi.add_argument(
        "--output-file",
        help="Exact MDX file path to write for the generated AsyncAPI page",
    )
    build_asyncapi.add_argument(
        "--overview-name",
        default="index.mdx",
        help="Filename for the overview page inside the output directory.",
    )
    build_asyncapi.add_argument(
        "--fixture-root",
        help="Directory to resolve manifest files from; defaults to the manifest directory",
    )
    build_asyncapi.add_argument(
        "--version",
        action="append",
        default=[],
        help="Version to include from the manifest. Repeat to include multiple versions.",
    )
    build_asyncapi.add_argument(
        "--publish-version",
        help="Version whose websocket surface should be published; defaults to the manifest or latest selected version.",
    )
    build_asyncapi.add_argument(
        "--source-name",
        help="Optional source label to record in the generated page.",
    )
    build_asyncapi.add_argument(
        "--version-filter",
        help="Optional label describing the selected version set.",
    )
    build_asyncapi.add_argument(
        "--page-title",
        default="AsyncAPI WebSocket Reference",
        help="Title to use for the generated page.",
    )
    build_asyncapi.add_argument(
        "--page-description",
        default="WebSocket AsyncAPI reference and version history.",
        help="Description to use for the generated page.",
    )
    build_asyncapi.add_argument(
        "--docs-json",
        help="Optional docs.json file to update with the generated page",
    )
    build_asyncapi.add_argument(
        "--nav-dropdown",
        help="Dropdown label in docs.json where the generated page should be inserted",
    )
    build_asyncapi.add_argument(
        "--nav-version",
        action="append",
        default=[],
        help="Version label under the selected dropdown to update. Repeat to target multiple versions. Defaults to all versions in the dropdown.",
    )
    build_asyncapi.add_argument(
        "--nav-group",
        action="append",
        default=[],
        help="Group label path under the selected dropdown/version where the page should be inserted. Repeat for nested groups.",
    )

    openrpc = subparsers.add_parser("openrpc", help="OpenRPC JSON-RPC commands")
    openrpc_subparsers = openrpc.add_subparsers(dest="openrpc_command", required=True)

    build_openrpc = openrpc_subparsers.add_parser(
        "build-api-pages-from-manifest",
        help="Build OpenRPC MDX pages directly from local OpenRPC snapshots",
    )
    build_openrpc.add_argument(
        "--manifest",
        required=True,
        help="Path to a JSON/YAML manifest that lists local OpenRPC snapshots",
    )
    build_openrpc.add_argument(
        "--output-dir",
        required=True,
        help="Directory where generated MDX pages should be written",
    )
    build_openrpc.add_argument(
        "--fixture-root",
        help="Directory to resolve manifest fixture paths from; defaults to the manifest directory",
    )
    build_openrpc.add_argument(
        "--version",
        action="append",
        default=[],
        help="Version to include from the manifest. Repeat to include multiple versions.",
    )
    build_openrpc.add_argument(
        "--publish-version",
        help="Version whose OpenRPC surface should be published; defaults to the manifest or latest selected version.",
    )
    build_openrpc.add_argument(
        "--source-name",
        help="Optional source label to record in the report",
    )
    build_openrpc.add_argument(
        "--version-filter",
        help="Optional label describing the selected version set.",
    )
    build_openrpc.add_argument(
        "--overview-name",
        default="index.mdx",
        help="Filename for the overview page inside the output directory",
    )
    build_openrpc.add_argument(
        "--spec-dir-name",
        default="specs",
        help="Directory name for per-spec pages inside the output directory.",
    )
    build_openrpc.add_argument(
        "--overview-title",
        default="Wallet Gateway OpenRPC",
        help="Title to use for the generated overview page.",
    )
    build_openrpc.add_argument(
        "--link-prefix",
        help="Optional root-relative URL prefix to use for overview/spec links.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-formats":
        print("jvm-docs")
        print("daml-json")
        print("protobuf")
        print("typedoc")
        print("asyncapi")
        print("openrpc")
        return 0

    if args.command == "jvm-docs":
        if args.jvm_docs_command == "build-api-pages-from-manifest":
            from x2mdx.jvm_docs.render import build_pages
            from x2mdx.mintlify import MintlifyNavTarget, update_docs_json_navigation
            from x2mdx.render import write_pages

            if (args.nav_dropdown or args.nav_version or args.nav_group) and not args.docs_json:
                parser.error("--nav-dropdown/--nav-version/--nav-group require --docs-json")
            if args.docs_json and not args.nav_dropdown:
                parser.error("--docs-json requires --nav-dropdown")

            report = build_jvm_doc_report_from_manifest_args(args)
            overview_file = Path(args.overview_file)
            details_dir = Path(args.details_dir)
            if overview_file.exists():
                overview_file.unlink()
            if details_dir.exists():
                shutil.rmtree(details_dir)
            output_root, pages = build_pages(
                report,
                overview_output=overview_file,
                details_dir=details_dir,
                overview_title=args.overview_title,
            )
            write_pages(pages, output_root)
            if args.docs_json:
                update_docs_json_navigation(
                    Path(args.docs_json),
                    output_file=overview_file,
                    target=MintlifyNavTarget(
                        dropdown=args.nav_dropdown,
                        versions=args.nav_version or None,
                        groups=args.nav_group,
                    ),
                )
            return 0

    if args.command == "daml-json":
        if args.daml_json_command == "build-api-pages-from-manifest":
            from x2mdx.daml_json.render import build_pages
            from x2mdx.render import write_pages

            report = build_daml_doc_report_from_manifest_args(args)
            output_root, pages = build_pages(
                report,
                output_dir=Path(args.output_dir),
                overview_title=args.overview_title,
                link_prefix=args.link_prefix,
            )
            write_pages(pages, output_root)
            return 0

    if args.command == "protobuf":
        if args.protobuf_command == "build-api-pages-from-manifest":
            from x2mdx.protobuf.render import build_pages
            from x2mdx.render import write_pages

            report = build_protobuf_report_from_manifest_args(args)
            output_dir = Path(args.output_dir)
            if output_dir.exists():
                shutil.rmtree(output_dir)
            output_root, pages = build_pages(report, output_dir=output_dir)
            write_pages(pages, output_root)
            return 0

    if args.command == "typedoc":
        if args.typedoc_command == "build-api-pages-from-manifest":
            from x2mdx.render import write_page
            from x2mdx.typedoc.render import build_page

            report = build_typedoc_report_from_manifest_args(args)
            output_file = Path(args.output_file)
            page = build_page(
                report,
                output_path=output_file.name,
                page_title=args.page_title,
                page_description=args.page_description,
            )
            write_page(page, output_file)
            return 0

    if args.command == "asyncapi":
        if args.asyncapi_command == "build-api-pages-from-manifest":
            from x2mdx.asyncapi.render import build_page, build_pages
            from x2mdx.mintlify import MintlifyNavTarget, update_docs_json_navigation
            from x2mdx.render import write_page, write_pages

            if (args.nav_dropdown or args.nav_version or args.nav_group) and not args.docs_json:
                parser.error("--nav-dropdown/--nav-version/--nav-group require --docs-json")
            if args.docs_json and not args.nav_dropdown:
                parser.error("--docs-json requires --nav-dropdown")
            if not args.output_dir and not args.output_file:
                parser.error("build-api-pages-from-manifest requires --output-dir or --output-file")
            if args.output_dir and args.output_file:
                parser.error("build-api-pages-from-manifest accepts only one of --output-dir or --output-file")

            report = build_asyncapi_report_from_manifest_args(args)
            if args.output_file:
                output_file = Path(args.output_file)
                page = build_page(
                    report,
                    output_path=output_file.name,
                    page_title=args.page_title,
                    page_description=args.page_description,
                )
                write_page(page, output_file)
            else:
                output_dir = Path(args.output_dir)
                if output_dir.exists():
                    shutil.rmtree(output_dir)
                output_root, pages = build_pages(
                    report,
                    output_dir=output_dir,
                    overview_name=args.overview_name,
                    page_title=args.page_title,
                    page_description=args.page_description,
                )
                write_pages(pages, output_root)
                output_file = output_dir / args.overview_name
            if args.docs_json:
                update_docs_json_navigation(
                    Path(args.docs_json),
                    output_file=output_file,
                    target=MintlifyNavTarget(
                        dropdown=args.nav_dropdown,
                        versions=args.nav_version or None,
                        groups=args.nav_group,
                    ),
                )
            return 0

    if args.command == "openrpc":
        if args.openrpc_command == "build-api-pages-from-manifest":
            from x2mdx.openrpc.render import build_pages
            from x2mdx.render import write_pages

            report = build_openrpc_report_from_manifest_args(args)
            output_dir = Path(args.output_dir)
            if output_dir.exists():
                shutil.rmtree(output_dir)
            output_root, pages = build_pages(
                report,
                output_dir=output_dir,
                overview_name=args.overview_name,
                spec_dir_name=args.spec_dir_name,
                overview_title=args.overview_title,
                link_prefix=args.link_prefix,
            )
            write_pages(pages, output_root)
            return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
