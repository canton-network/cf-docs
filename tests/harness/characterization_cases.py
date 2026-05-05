from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "characterization"


@dataclass(frozen=True)
class CharacterizationPreview:
    format_group: str
    case_label: str
    description: str
    target_root: str
    entry_file: str
    entry_source_file: str | None = None
    link_rewrites: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CharacterizationCase:
    name: str
    argv_factory: Callable[[Path], list[str]]
    preview: CharacterizationPreview
    expected_file: Path | None = None
    actual_file: str | None = None
    expected_tree: Path | None = None
    actual_tree: str | None = None
    docs_json_before: Path | None = None
    docs_json_after: Path | None = None
    actual_docs_json: str | None = None


def jvm_docs_args(root: Path) -> list[str]:
    overview_file = root / "docs-main" / "reference" / "ledger-api-jvm-bindings.mdx"
    details_dir = root / "docs-main" / "reference" / "details"
    docs_json = root / "docs-main" / "docs.json"
    return [
        "jvm-docs",
        "build-api-pages-from-manifest",
        "--manifest",
        str(FIXTURE_ROOT / "jvm_docs" / "input" / "manifest.json"),
        "--overview-file",
        str(overview_file),
        "--details-dir",
        str(details_dir),
        "--docs-json",
        str(docs_json),
        "--nav-dropdown",
        "Reference",
        "--source-name",
        "Published DAML Java/Scala bindings Javadoc/Scaladoc jars",
        "--version-filter",
        "characterization fixture versions",
    ]


def daml_json_args(root: Path) -> list[str]:
    return [
        "daml-json",
        "build-api-pages-from-manifest",
        "--manifest",
        str(FIXTURE_ROOT / "daml_json" / "input" / "manifest.json"),
        "--output-dir",
        str(root / "daml_json"),
        "--publish-version",
        "3.4.11",
        "--overview-title",
        "Daml Standard Library",
        "--source-name",
        "Published Daml Standard Library docs JSON from local SDK artifacts",
        "--version-filter",
        "characterization fixture versions",
        "--link-prefix",
        "/appdev/reference/daml-standard-library",
    ]


def protobuf_args(root: Path) -> list[str]:
    return [
        "protobuf",
        "build-api-pages-from-manifest",
        "--manifest",
        str(FIXTURE_ROOT / "protobuf" / "input" / "manifest.json"),
        "--output-dir",
        str(root / "expected"),
        "--source-name",
        "Canton protobuf descriptor snapshots from release tags",
        "--version-filter",
        "characterization fixture versions",
    ]


def typedoc_args(root: Path) -> list[str]:
    return [
        "typedoc",
        "build-api-pages-from-manifest",
        "--manifest",
        str(FIXTURE_ROOT / "typedoc" / "input" / "manifest.json"),
        "--output-file",
        str(root / "typedoc" / "typescript.mdx"),
        "--publish-version",
        "3.4.11",
        "--source-name",
        "Published @daml/types npm tarballs rendered to local TypeDoc JSON",
        "--version-filter",
        "characterization fixture versions",
        "--page-title",
        "TypeScript",
        "--page-description",
        "TypeScript and JavaScript language bindings for Canton.",
    ]


def asyncapi_args(root: Path) -> list[str]:
    output_file = root / "docs-main" / "reference" / "json-api-asyncapi-reference.mdx"
    docs_json = root / "docs-main" / "docs.json"
    return [
        "asyncapi",
        "build-api-pages-from-manifest",
        "--manifest",
        str(FIXTURE_ROOT / "asyncapi" / "input" / "manifest.json"),
        "--output-file",
        str(output_file),
        "--publish-version",
        "3.4.12",
        "--source-name",
        "splice-wallet-kernel Ledger API AsyncAPI snapshots",
        "--version-filter",
        "characterization fixture versions",
        "--page-title",
        "JSON API AsyncAPI Reference",
        "--page-description",
        "JSON Ledger API WebSocket AsyncAPI reference and version history.",
        "--docs-json",
        str(docs_json),
        "--nav-dropdown",
        "Reference",
        "--nav-group",
        "Ledger API Endpoints",
    ]


def openrpc_default_args(root: Path) -> list[str]:
    return [
        "openrpc",
        "build-api-pages-from-manifest",
        "--manifest",
        str(FIXTURE_ROOT / "openrpc" / "input" / "manifest.json"),
        "--fixture-root",
        str(REPO_ROOT),
        "--output-dir",
        str(root / "openrpc"),
        "--publish-version",
        "0.21.0",
        "--source-name",
        "splice-wallet-kernel Wallet Gateway OpenRPC release-tag snapshots",
        "--version-filter",
        "characterization fixture versions",
        "--link-prefix",
        "/reference/wallet-gateway-json-rpc",
    ]


def openrpc_alt_layout_args(root: Path) -> list[str]:
    return [
        "openrpc",
        "build-api-pages-from-manifest",
        "--manifest",
        str(FIXTURE_ROOT / "openrpc" / "input" / "manifest.json"),
        "--fixture-root",
        str(REPO_ROOT),
        "--output-dir",
        str(root / "openrpc-alt"),
        "--publish-version",
        "0.21.0",
        "--source-name",
        "splice-wallet-kernel Wallet Gateway OpenRPC release-tag snapshots",
        "--version-filter",
        "characterization fixture versions",
        "--overview-name",
        "wallet-gateway-overview.mdx",
        "--spec-dir-name",
        "rpc-specs",
        "--link-prefix",
        "/reference/wallet-gateway-json-rpc",
    ]


CHARACTERIZATION_CASES = [
    CharacterizationCase(
        name="jvm docs docs layout with navigation",
        argv_factory=jvm_docs_args,
        preview=CharacterizationPreview(
            format_group="JVM Docs",
            case_label="Overview and details layout",
            description="Docs-style JVM overview page, details tree, and frozen Reference dropdown insertion behavior.",
            target_root="reference/jvm-docs-layout",
            entry_file="ledger-api-jvm-bindings.mdx",
        ),
        expected_tree=FIXTURE_ROOT / "jvm_docs" / "expected_docs_layout",
        actual_tree="docs-main/reference",
        docs_json_before=FIXTURE_ROOT / "jvm_docs" / "docs_json.before.json",
        docs_json_after=FIXTURE_ROOT / "jvm_docs" / "docs_json.after.json",
        actual_docs_json="docs-main/docs.json",
    ),
    CharacterizationCase(
        name="daml json published layout",
        argv_factory=daml_json_args,
        preview=CharacterizationPreview(
            format_group="DAML JSON",
            case_label="Published layout",
            description="Published Daml Standard Library layout with the real absolute link prefix preserved.",
            target_root="appdev/reference/daml-standard-library",
            entry_file="index.mdx",
        ),
        expected_tree=FIXTURE_ROOT / "daml_json" / "expected",
        actual_tree="daml_json",
    ),
    CharacterizationCase(
        name="protobuf docs-backed title output",
        argv_factory=protobuf_args,
        preview=CharacterizationPreview(
            format_group="Protobuf",
            case_label="Generated package tree",
            description="Generated protobuf index plus package pages from the checked-in Canton descriptor fixtures.",
            target_root="reference/protobuf-history",
            entry_file="index.mdx",
        ),
        expected_tree=FIXTURE_ROOT / "protobuf" / "expected",
        actual_tree="expected",
    ),
    CharacterizationCase(
        name="typedoc single page",
        argv_factory=typedoc_args,
        preview=CharacterizationPreview(
            format_group="TypeDoc",
            case_label="Single page",
            description="Single generated TypeDoc page from the frozen @daml/types characterization fixture.",
            target_root="reference/typedoc",
            entry_file="typescript.mdx",
        ),
        expected_file=FIXTURE_ROOT / "typedoc" / "expected" / "typescript.mdx",
        actual_file="typedoc/typescript.mdx",
    ),
    CharacterizationCase(
        name="asyncapi page with docs navigation",
        argv_factory=asyncapi_args,
        preview=CharacterizationPreview(
            format_group="AsyncAPI",
            case_label="Single page with docs navigation",
            description="Single generated AsyncAPI page plus the frozen Reference dropdown group insertion behavior.",
            target_root="reference/asyncapi-single-file",
            entry_file="json-api-asyncapi-reference.mdx",
        ),
        expected_file=FIXTURE_ROOT / "asyncapi" / "expected" / "ledger-api-websocket-reference.mdx",
        actual_file="docs-main/reference/json-api-asyncapi-reference.mdx",
        docs_json_before=FIXTURE_ROOT / "asyncapi" / "docs_json.before.json",
        docs_json_after=FIXTURE_ROOT / "asyncapi" / "docs_json.after.json",
        actual_docs_json="docs-main/docs.json",
    ),
    CharacterizationCase(
        name="openrpc docs-backed layout",
        argv_factory=openrpc_default_args,
        preview=CharacterizationPreview(
            format_group="OpenRPC",
            case_label="Docs-backed layout",
            description="Overview plus specs using the standard Wallet Gateway JSON-RPC layout and link prefix.",
            target_root="reference/wallet-gateway-json-rpc",
            entry_file="index.mdx",
        ),
        expected_tree=FIXTURE_ROOT / "openrpc" / "expected",
        actual_tree="openrpc",
    ),
    CharacterizationCase(
        name="openrpc alternate layout",
        argv_factory=openrpc_alt_layout_args,
        preview=CharacterizationPreview(
            format_group="OpenRPC",
            case_label="Alternate layout",
            description="Alternate overview and specs layout staged under a preview-only path to avoid clobbering the standard Wallet Gateway layout.",
            target_root="reference/wallet-gateway-json-rpc-alt",
            entry_file="index.mdx",
            entry_source_file="wallet-gateway-overview.mdx",
            link_rewrites=(
                (
                    "/reference/wallet-gateway-json-rpc",
                    "/reference/wallet-gateway-json-rpc-alt",
                ),
            ),
        ),
        expected_tree=FIXTURE_ROOT / "openrpc" / "expected_alt_layout",
        actual_tree="openrpc-alt",
    ),
]
