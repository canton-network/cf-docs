#!/usr/bin/env python3

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from docs_env import ensure_repo_direnv, repo_direnv_command
import generated_reference_nav
import reference_nav


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "protobuf-history" / "source-artifacts.json"
DEFAULT_CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "x2mdx"
DEFAULT_CACHE_DIR = DEFAULT_CACHE_ROOT / "protobuf-history"
DEFAULT_MANIFEST = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "protobuf-history" / "manifest.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs-main" / "appdev" / "reference" / "protobuf-history"
DEFAULT_LEGACY_OUTPUT_DIR = REPO_ROOT / "docs-main" / "reference" / "protobuf"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
DEFAULT_REPO_DIR = DEFAULT_CACHE_DIR / "repos" / "canton"
GROUP_LABEL = "Canton Protobuf History"
DETAILS_LABEL = "Details and History"
DESCRIPTOR_IMAGE_NAME = ".proto_snapshot_image.bin.gz"
STABLE_TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
SECTION_TO_REPO_PREFIX = {
    "admin-api": "community/admin-api/src/main/protobuf",
    "community": "community/base/src/main/protobuf",
    "ledger-api": "community/ledger-api/src/main/protobuf",
    "participant": "community/participant/src/main/protobuf",
    "synchronizer": "community/synchronizer/src/main/protobuf",
}
SUPPORT_SECTION_NAMES = {"lib"}
USER_AGENT = "digital-asset-docs-x2mdx/1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Canton release-bundle protobuf inputs, write an x2mdx manifest, and render protobuf history MDX."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--manifest-out", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--legacy-output-dir", default=str(DEFAULT_LEGACY_OUTPUT_DIR))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--nav-dropdown", default="API Reference")
    parser.add_argument("--nav-group", action="append")
    parser.add_argument("--repo-dir", default=str(DEFAULT_REPO_DIR))
    parser.add_argument("--version", action="append", help="Explicit version to include. Repeat to limit generation.")
    parser.add_argument("--min-version", help="Minimum stable version to include when auto-discovering tags.")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetching tags from origin before generation.")
    parser.add_argument("--force-refresh", action="store_true", help="Refresh cached protobuf bundles and descriptor images.")
    parser.add_argument(
        "--source-name",
        default="Canton protobuf trees from published release bundles",
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


def load_excluded_versions(source_config: dict[str, Any]) -> set[str]:
    configured = source_config.get("excluded_versions")
    if configured is None:
        return set()
    if not isinstance(configured, list) or not all(isinstance(item, str) and item for item in configured):
        raise ValueError("Source config excluded_versions must be a list of non-empty strings")
    return set(configured)


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


def git(args: list[str], *, cwd: Path, capture: bool = False) -> str:
    return run(["git", *args], cwd=cwd, capture=capture)


def ensure_repo(repo_dir: Path, *, remote: str, fetch: bool) -> Path:
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if not repo_dir.exists():
        run(["git", "clone", "--bare", remote, str(repo_dir)])
    if fetch:
        git(["fetch", "origin", "--tags", "--prune"], cwd=repo_dir)
    return repo_dir


def semver_key(version: str) -> tuple[int, int, int]:
    match = STABLE_TAG_RE.fullmatch(f"v{version}" if not version.startswith("v") else version)
    if not match:
        raise ValueError(f"Expected stable semver version, got: {version}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def stable_tags(repo_dir: Path, *, min_version: str, include_versions: set[str] | None) -> list[tuple[str, str]]:
    tags_raw = git(["tag", "--list", "v*"], cwd=repo_dir, capture=True)
    selected: list[tuple[str, str]] = []
    min_key = semver_key(min_version)
    for line in tags_raw.splitlines():
        tag = line.strip()
        match = STABLE_TAG_RE.fullmatch(tag)
        if not match:
            continue
        version = tag.removeprefix("v")
        if semver_key(version) < min_key:
            continue
        if include_versions is not None and version not in include_versions:
            continue
        selected.append((version, tag))
    selected.sort(key=lambda item: semver_key(item[0]))
    return selected


def release_date(repo_dir: Path, tag: str) -> str | None:
    date = git(
        ["for-each-ref", "--format=%(creatordate:short)", f"refs/tags/{tag}"],
        cwd=repo_dir,
        capture=True,
    )
    return date or None


def bundle_url(source_config: dict[str, Any], *, version: str) -> str:
    template = source_config.get("release_url_template")
    if not isinstance(template, str) or not template:
        raise ValueError("Source config must define `release_url_template`")
    return template.format(version=version)


def bundle_archive_name(version: str) -> str:
    return f"canton-open-source-{version}.tar.gz"


def bundle_archive_path(cache_dir: Path, version: str) -> Path:
    return cache_dir / "release-bundles" / version / bundle_archive_name(version)


def bundle_extract_root(cache_dir: Path, version: str) -> Path:
    return cache_dir / "bundles" / version


def descriptor_image_path(cache_dir: Path, version: str) -> Path:
    return cache_dir / "descriptor-images" / version / DESCRIPTOR_IMAGE_NAME


def ensure_bundle_archive(
    *,
    source_config: dict[str, Any],
    version: str,
    output_path: Path,
    force_refresh: bool,
) -> Path:
    if output_path.exists() and not force_refresh:
        return output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.name}.{os.getpid()}.tmp")
    request = urllib.request.Request(bundle_url(source_config, version=version), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response, temp_path.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    temp_path.replace(output_path)
    return output_path


def extract_archive(archive_path: Path, *, extract_root: Path, bundle_proto_dir: str, force_refresh: bool) -> Path:
    if extract_root.exists() and force_refresh:
        shutil.rmtree(extract_root)
    if not extract_root.exists():
        extract_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as handle:
            handle.extractall(extract_root, filter="data")

    candidates = sorted(path for path in extract_root.rglob(bundle_proto_dir) if path.is_dir())
    if not candidates:
        raise FileNotFoundError(f"Could not locate extracted '{bundle_proto_dir}' directory under {extract_root}")
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


def replace_text(path: Path, replacements: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    updated = text
    for old, new in replacements:
        updated = updated.replace(old, new)
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def retitle_overview_page(path: Path) -> None:
    replace_text(
        path,
        [
            ('title: "Canton Protobuf History"', f'title: "{DETAILS_LABEL}"'),
            ('title: "Canton Protobuf Reference"', f'title: "{DETAILS_LABEL}"'),
            ('title: "Canton Protobuf References"', f'title: "{DETAILS_LABEL}"'),
            (
                '<h1 class="x2mdx-ref-title">Canton Protobuf Reference</h1>',
                f'<h1 class="x2mdx-ref-title">{DETAILS_LABEL}</h1>',
            ),
            (
                '<h1 class="x2mdx-ref-title">Canton Protobuf References</h1>',
                f'<h1 class="x2mdx-ref-title">{DETAILS_LABEL}</h1>',
            ),
        ],
    )


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
    output_dir: Path,
    legacy_overview_path: Path,
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

    page_ref = docs_json_page_ref(output_dir / "index.mdx", docs_json_path)
    legacy_page_ref = docs_json_page_ref(legacy_overview_path, docs_json_path)
    dropdown["pages"] = prune_nav_items(
        pages,
        page_refs={page_ref, legacy_page_ref},
        group_labels=reference_nav.PROTOBUF_GROUP_ALIASES,
    )
    target_pages = ensure_group_path(dropdown["pages"], parent_groups)
    target_pages.append({"group": GROUP_LABEL, "pages": [page_ref, legacy_page_ref]})
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
        "source": source_config.get("source") or "Canton protobuf trees from published release bundles",
        "repo": source_config.get("repo") if isinstance(source_config.get("repo"), dict) else {},
        "metadata_path": metadata_ref,
        "versions": releases,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    return manifest_path


def sync_output_tree(*, source_dir: Path, target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)
    print(f"Synced output tree: {target_dir}")


def main() -> int:
    ensure_repo_direnv(repo_root=REPO_ROOT, script_path=Path(__file__).resolve(), argv=sys.argv[1:])
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    repo_config = source_config.get("repo") if isinstance(source_config.get("repo"), dict) else {}
    remote = repo_config.get("remote")
    if not isinstance(remote, str) or not remote:
        raise ValueError("Source config must define repo.remote")
    bundle_proto_dir = source_config.get("bundle_proto_dir") or "protobuf"
    if not isinstance(bundle_proto_dir, str) or not bundle_proto_dir:
        raise ValueError("Source config must define bundle_proto_dir")

    include_versions = set(args.version) if args.version else None
    excluded_versions = load_excluded_versions(source_config)
    if include_versions is not None:
        include_versions -= excluded_versions
    min_version = args.min_version or source_config.get("min_version") or "0.0.0"
    if not isinstance(min_version, str):
        raise ValueError("min_version must be a string")

    repo_dir = ensure_repo(Path(args.repo_dir).resolve(), remote=remote, fetch=not args.skip_fetch)
    selected_tags = stable_tags(repo_dir, min_version=min_version, include_versions=include_versions)
    if excluded_versions:
        selected_tags = [(version, tag) for version, tag in selected_tags if version not in excluded_versions]
    if not selected_tags:
        raise ValueError("No stable Canton tags selected")
    cache_dir = Path(args.cache_dir).resolve()
    releases: list[dict[str, Any]] = []
    for version, tag in selected_tags:
        archive_path = ensure_bundle_archive(
            source_config=source_config,
            version=version,
            output_path=bundle_archive_path(cache_dir, version),
            force_refresh=args.force_refresh,
        )
        protobuf_root = extract_archive(
            archive_path,
            extract_root=bundle_extract_root(cache_dir, version),
            bundle_proto_dir=bundle_proto_dir,
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
                "date": release_date(repo_dir, tag),
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
            version_filter = "selected Canton release bundles"
        else:
            version_filter = f"stable Canton release bundles >= {min_version}"

    command = repo_direnv_command(
        REPO_ROOT,
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
    )
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode != 0:
        return completed.returncode

    retitle_overview_page(Path(args.output_dir).resolve() / "index.mdx")
    sync_output_tree(
        source_dir=Path(args.output_dir).resolve(),
        target_dir=Path(args.legacy_output_dir).resolve(),
    )

    update_docs_navigation(
        docs_json_path=Path(args.docs_json).resolve(),
        dropdown_label=args.nav_dropdown,
        parent_groups=args.nav_group or [],
        output_dir=Path(args.output_dir).resolve(),
        legacy_overview_path=Path(args.legacy_output_dir).resolve() / "index.mdx",
    )
    reference_nav.regroup_ledger_api_nav(
        docs_json_path=Path(args.docs_json).resolve(),
        dropdown_label=args.nav_dropdown,
    )
    generated_reference_nav.replace_group_in_dropdown(
        docs_json_path=Path(args.docs_json).resolve(),
        dropdown_label=args.nav_dropdown,
        group=generated_reference_nav.build_protobuf_nav_group(
            output_dir=Path(args.legacy_output_dir).resolve(),
            docs_json_path=Path(args.docs_json).resolve(),
            group_label=reference_nav.PROTOBUF_GROUP,
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
