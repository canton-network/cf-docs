#!/usr/bin/env python3

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "protobuf-history" / "source-artifacts.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "protobuf-history"
DEFAULT_MANIFEST = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "protobuf-history" / "manifest.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs-main" / "appdev" / "reference" / "protobuf-history"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
GROUP_LABEL = "Canton Protobuf History"
DESCRIPTOR_IMAGE_NAME = ".proto_snapshot_image.bin.gz"
STABLE_TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
RELEASE_REPO_DEFAULT = "DACH-NY/canton"
SECTION_TO_REPO_PREFIX = {
    "admin-api": "community/admin-api/src/main/protobuf",
    "community": "community/base/src/main/protobuf",
    "ledger-api": "community/ledger-api/src/main/protobuf",
    "participant": "community/participant/src/main/protobuf",
    "synchronizer": "community/synchronizer/src/main/protobuf",
}
SUPPORT_SECTION_NAMES = {"lib"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch published Canton protobuf bundles, write an x2mdx manifest, and render protobuf history MDX."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--manifest-out", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--nav-dropdown", default="Reference")
    parser.add_argument("--nav-group", action="append")
    parser.add_argument("--version", action="append", help="Explicit version to include. Repeat to limit generation.")
    parser.add_argument("--min-version", help="Minimum stable version to include when auto-discovering releases.")
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Ignored; retained for compatibility with the old repo-tag flow.",
    )
    parser.add_argument("--force-refresh", action="store_true", help="Refresh cached protobuf bundles and descriptor images.")
    parser.add_argument(
        "--source-name",
        default="Published Canton protobuf release bundles",
        help="Source label embedded in generated content.",
    )
    parser.add_argument(
        "--version-filter",
        help="Version-filter label embedded in generated content.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def run(args: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd) if cwd else None,
        "check": True,
        "text": True,
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    completed = subprocess.run(args, **kwargs)
    return completed.stdout.strip() if capture else ""


def gh(args: list[str], *, capture: bool = False) -> str:
    return run(["gh", *args], capture=capture)


def semver_key(version: str) -> tuple[int, int, int]:
    match = STABLE_TAG_RE.fullmatch(f"v{version}" if not version.startswith("v") else version)
    if not match:
        raise ValueError(f"Expected stable semver version, got: {version}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def stable_releases(release_repo: str, *, min_version: str, include_versions: set[str] | None) -> list[dict[str, str | None]]:
    releases_raw = gh(
        ["release", "list", "-R", release_repo, "--json", "tagName,publishedAt", "--limit", "200"],
        capture=True,
    )
    releases_payload = json.loads(releases_raw)
    if not isinstance(releases_payload, list):
        raise ValueError(f"Expected release list from gh for {release_repo}")

    selected: list[dict[str, str | None]] = []
    min_key = semver_key(min_version)
    for entry in releases_payload:
        if not isinstance(entry, dict):
            continue
        tag = entry.get("tagName")
        if not isinstance(tag, str):
            continue
        if not STABLE_TAG_RE.fullmatch(tag):
            continue
        version = tag.removeprefix("v")
        if semver_key(version) < min_key:
            continue
        if include_versions is not None and version not in include_versions:
            continue
        published_at = entry.get("publishedAt")
        selected.append(
            {
                "version": version,
                "tag": tag,
                "date": published_at[:10] if isinstance(published_at, str) and published_at else None,
            }
        )
    selected.sort(key=lambda item: semver_key(str(item["version"])))
    return selected


def release_details(release_repo: str, tag: str) -> dict[str, Any]:
    details_raw = gh(
        ["release", "view", tag, "-R", release_repo, "--json", "assets,tagName,url,name,publishedAt"],
        capture=True,
    )
    details = json.loads(details_raw)
    if not isinstance(details, dict):
        raise ValueError(f"Expected release details from gh for {release_repo} {tag}")
    return details


def select_asset_name(assets: list[Any], *, version: str, patterns: list[str]) -> str | None:
    asset_names = {asset.get("name") for asset in assets if isinstance(asset, dict) and isinstance(asset.get("name"), str)}
    for pattern in patterns:
        candidate = pattern.format(version=version)
        if candidate in asset_names:
            return candidate
    return None


def asset_archive_path(cache_dir: Path, version: str, asset_name: str) -> Path:
    return cache_dir / "release-assets" / version / asset_name


def bundle_extract_root(cache_dir: Path, version: str) -> Path:
    return cache_dir / "bundles" / version


def descriptor_image_path(cache_dir: Path, version: str) -> Path:
    return cache_dir / "descriptor-images" / version / DESCRIPTOR_IMAGE_NAME


def ensure_release_asset(
    release_repo: str,
    *,
    tag: str,
    asset_name: str,
    output_path: Path,
    force_refresh: bool,
) -> Path:
    if output_path.exists() and not force_refresh:
        return output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gh(
        [
            "release",
            "download",
            tag,
            "-R",
            release_repo,
            "-p",
            asset_name,
            "-D",
            str(output_path.parent),
            "--clobber",
        ]
    )
    if not output_path.exists():
        raise FileNotFoundError(f"Expected downloaded asset at {output_path}")
    return output_path


def extract_archive(archive_path: Path, *, extract_root: Path, force_refresh: bool) -> Path:
    if extract_root.exists() and force_refresh:
        shutil.rmtree(extract_root)
    if not extract_root.exists():
        extract_root.mkdir(parents=True, exist_ok=True)
        if archive_path.name.endswith(".tar.gz"):
            with tarfile.open(archive_path, "r:gz") as handle:
                handle.extractall(extract_root, filter="data")
        elif archive_path.suffix == ".zip":
            with zipfile.ZipFile(archive_path) as handle:
                handle.extractall(extract_root)
        else:
            raise ValueError(f"Unsupported protobuf archive format: {archive_path.name}")

    candidates = sorted(path for path in extract_root.rglob("protobuf") if path.is_dir())
    if not candidates:
        raise FileNotFoundError(f"Could not locate extracted protobuf directory under {extract_root}")
    return candidates[0]


def ensure_grpc_tools_available() -> None:
    if importlib.util.find_spec("grpc_tools.protoc") is None:
        raise RuntimeError(
            "Missing grpc_tools.protoc. Use the repo's nix shell or install grpcio-tools in the active Python environment."
        )


def compile_descriptor_image(protobuf_root: Path, *, output_path: Path) -> None:
    ensure_grpc_tools_available()
    include_roots: list[Path] = []
    for section_name in [*SECTION_TO_REPO_PREFIX, *SUPPORT_SECTION_NAMES]:
        section_root = protobuf_root / section_name
        if section_root.is_dir():
            include_roots.append(section_root)
    if not include_roots:
        raise ValueError(f"No protobuf source roots found under {protobuf_root}")

    rel_files: list[str] = []
    seen: set[str] = set()
    for include_root in include_roots:
        for proto_path in sorted(include_root.rglob("*.proto")):
            rel = proto_path.relative_to(include_root).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            rel_files.append(rel)
    if not rel_files:
        raise ValueError(f"No .proto files found under {protobuf_root}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        raw_descriptor = temp_dir / "descriptor.pb"
        command = [sys.executable, "-m", "grpc_tools.protoc"]
        for include_root in include_roots:
            command.extend(["-I", str(include_root)])
        command.extend(["--descriptor_set_out", str(raw_descriptor), "--include_imports", *rel_files])
        run(command, cwd=protobuf_root)
        output_path.write_bytes(gzip.compress(raw_descriptor.read_bytes()))


def import_to_repo_path_from_bundle(protobuf_root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for section_name, repo_prefix in SECTION_TO_REPO_PREFIX.items():
        section_root = protobuf_root / section_name
        if not section_root.is_dir():
            continue
        for proto_path in sorted(section_root.rglob("*.proto")):
            import_path = proto_path.relative_to(section_root).as_posix()
            repo_path = f"{repo_prefix}/{import_path}"
            existing = mapping.get(import_path)
            if existing and existing != repo_path:
                raise ValueError(f"Duplicate protobuf import path '{import_path}' in published bundle")
            mapping[import_path] = repo_path
    return mapping


def docs_json_page_ref(path: Path, docs_json_path: Path) -> str:
    relative = path.resolve().relative_to(docs_json_path.resolve().parent)
    if relative.suffix != ".mdx":
        raise ValueError(f"Expected MDX file under docs root, got: {path}")
    return relative.with_suffix("").as_posix()


def prune_nav_items(items: list[Any], *, page_refs: set[str], group_labels: set[str]) -> list[Any]:
    pruned: list[Any] = []
    for item in items:
        if isinstance(item, str):
            if item not in page_refs:
                pruned.append(item)
            continue
        if isinstance(item, dict):
            if item.get("group") in group_labels:
                continue
            updated = dict(item)
            pages = updated.get("pages")
            if isinstance(pages, list):
                updated["pages"] = prune_nav_items(pages, page_refs=page_refs, group_labels=group_labels)
            pruned.append(updated)
            continue
        pruned.append(item)
    return pruned


def ensure_group_path(items: list[Any], group_path: list[str]) -> list[Any]:
    current_pages = items
    for label in group_path:
        group = next((item for item in current_pages if isinstance(item, dict) and item.get("group") == label), None)
        if group is None:
            group = {"group": label, "pages": []}
            current_pages.append(group)
        pages = group.get("pages")
        if not isinstance(pages, list):
            pages = []
            group["pages"] = pages
        current_pages = pages
    return current_pages


def update_docs_navigation(
    *,
    docs_json_path: Path,
    dropdown_label: str,
    parent_groups: list[str],
    overview_path: Path,
) -> None:
    docs = load_json(docs_json_path)
    navigation = docs.get("navigation")
    if not isinstance(navigation, dict):
        raise ValueError(f"docs.json navigation must be an object: {docs_json_path}")
    dropdowns = navigation.get("dropdowns")
    if not isinstance(dropdowns, list):
        raise ValueError(f"docs.json navigation.dropdowns must be a list: {docs_json_path}")
    dropdown = next((item for item in dropdowns if isinstance(item, dict) and item.get("dropdown") == dropdown_label), None)
    if dropdown is None:
        raise ValueError(f"Dropdown not found in docs.json: {dropdown_label}")
    pages = dropdown.get("pages")
    if not isinstance(pages, list):
        raise ValueError(f"Dropdown does not expose a pages list: {dropdown_label}")

    page_ref = docs_json_page_ref(overview_path, docs_json_path)
    dropdown["pages"] = prune_nav_items(pages, page_refs={page_ref}, group_labels={GROUP_LABEL})
    target_pages = ensure_group_path(dropdown["pages"], parent_groups)
    target_pages.append({"group": GROUP_LABEL, "pages": [page_ref]})
    docs_json_path.write_text(json.dumps(docs, indent=2) + "\n", encoding="utf-8")
    print(f"Updated docs navigation: {docs_json_path}")


def write_manifest(
    *,
    source_config: dict[str, Any],
    releases: list[dict[str, Any]],
    manifest_path: Path,
) -> Path:
    metadata_path = source_config.get("metadata_path")
    metadata_ref: str | None = None
    if isinstance(metadata_path, str) and metadata_path:
        resolved = Path(metadata_path)
        if not resolved.is_absolute():
            resolved = (REPO_ROOT / resolved).resolve()
        metadata_ref = str(resolved)

    manifest = {
        "source": source_config.get("source") or "Published Canton protobuf release bundles",
        "repo": source_config.get("repo") if isinstance(source_config.get("repo"), dict) else {},
        "metadata_path": metadata_ref,
        "versions": releases,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    return manifest_path


def main() -> int:
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    release_repo = source_config.get("release_repo") or RELEASE_REPO_DEFAULT
    if not isinstance(release_repo, str) or not release_repo:
        raise ValueError("Source config must define release_repo")
    asset_patterns = source_config.get("asset_patterns")
    if not isinstance(asset_patterns, list) or not all(isinstance(item, str) for item in asset_patterns):
        raise ValueError("Source config must define asset_patterns as a list of strings")

    include_versions = set(args.version) if args.version else None
    min_version = args.min_version or source_config.get("min_version") or "0.0.0"
    if not isinstance(min_version, str):
        raise ValueError("min_version must be a string")

    selected_releases = stable_releases(release_repo, min_version=min_version, include_versions=include_versions)
    if not selected_releases:
        raise ValueError("No stable Canton releases selected")

    cache_dir = Path(args.cache_dir).resolve()
    releases: list[dict[str, Any]] = []
    for selected in selected_releases:
        version = str(selected["version"])
        tag = str(selected["tag"])
        details = release_details(release_repo, tag)
        assets = details.get("assets") if isinstance(details.get("assets"), list) else []
        asset_name = select_asset_name(assets, version=version, patterns=list(asset_patterns))
        if asset_name is None:
            print(f"Skipping {tag}: no matching published protobuf asset")
            continue
        archive_path = ensure_release_asset(
            release_repo,
            tag=tag,
            asset_name=asset_name,
            output_path=asset_archive_path(cache_dir, version, asset_name),
            force_refresh=args.force_refresh,
        )
        protobuf_root = extract_archive(
            archive_path,
            extract_root=bundle_extract_root(cache_dir, version),
            force_refresh=args.force_refresh,
        )
        import_to_repo_path = import_to_repo_path_from_bundle(protobuf_root)
        if not import_to_repo_path:
            print(f"Skipping {tag}: no published owned protobuf files found")
            continue
        image_path = descriptor_image_path(cache_dir, version)
        if not image_path.exists() or args.force_refresh:
            compile_descriptor_image(protobuf_root, output_path=image_path)
        releases.append(
            {
                "version": version,
                "tag": tag,
                "date": selected["date"],
                "descriptor_image_path": str(image_path.resolve()),
                "import_to_repo_path": import_to_repo_path,
            }
        )

    if not releases:
        raise ValueError("No protobuf releases were materialized")

    manifest_path = write_manifest(
        source_config=source_config,
        releases=releases,
        manifest_path=Path(args.manifest_out).resolve(),
    )

    version_filter = args.version_filter
    if not version_filter:
        if include_versions:
            version_filter = "selected published Canton releases"
        else:
            version_filter = f"published stable Canton releases >= {min_version}"

    command = [
        "x2mdx",
        "protobuf",
        "build-api-pages-from-manifest",
        "--manifest",
        str(manifest_path),
        "--output-dir",
        str(Path(args.output_dir).resolve()),
        "--source-name",
        args.source_name,
        "--version-filter",
        version_filter,
    ]
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode != 0:
        return completed.returncode

    update_docs_navigation(
        docs_json_path=Path(args.docs_json).resolve(),
        dropdown_label=args.nav_dropdown,
        parent_groups=args.nav_group or [],
        overview_path=Path(args.output_dir).resolve() / "index.mdx",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
