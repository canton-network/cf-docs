#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "protobuf-history" / "source-artifacts.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "protobuf-history"
DEFAULT_MANIFEST = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "protobuf-history" / "manifest.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs-main" / "appdev" / "reference" / "protobuf-history"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
DEFAULT_REPO_DIR = DEFAULT_CACHE_DIR / "repos" / "canton"
GROUP_LABEL = "Canton Protobuf History"
DESCRIPTOR_IMAGE_NAME = ".proto_snapshot_image.bin.gz"
STABLE_TAG_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
OWNED_PROTO_RE = re.compile(r"^community/.+/src/main/protobuf/.+\.proto$")
PACKAGE_GROUP_ORDER = [
    "Ledger API",
    "Participant Administration",
    "Sequencer",
    "Mediator",
    "Shared Administration",
    "Other APIs",
    "Schema Packages",
]
TITLE_RE = re.compile(r'^title: "(?P<title>.+)"$', re.MULTILINE)
CURRENT_SERVICES_RE = re.compile(r"^- Current services: `(?P<count>\d+)`$", re.MULTILINE)
CURRENT_ENDPOINTS_RE = re.compile(r"^- Current endpoints: `(?P<count>\d+)`$", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Canton release-tag protobuf inputs, write an x2mdx manifest, and render protobuf history MDX."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--manifest-out", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--nav-dropdown", default="Reference")
    parser.add_argument("--nav-group", action="append")
    parser.add_argument("--repo-dir", default=str(DEFAULT_REPO_DIR))
    parser.add_argument("--version", action="append", help="Explicit version to include. Repeat to limit generation.")
    parser.add_argument("--min-version", help="Minimum stable version to include when auto-discovering tags.")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetching tags from origin before generation.")
    parser.add_argument("--force-refresh", action="store_true", help="Refresh cached descriptor images even if present.")
    parser.add_argument(
        "--source-name",
        default="Canton protobuf descriptor snapshots from release tags",
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


def git(args: list[str], *, cwd: Path, capture: bool = False) -> str:
    return run(["git", *args], cwd=cwd, capture=capture)


def git_bytes(args: list[str], *, cwd: Path) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def git_try_bytes(args: list[str], *, cwd: Path) -> bytes | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout


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


def list_owned_proto_paths(repo_dir: Path, tag: str) -> list[str]:
    tree = git(["ls-tree", "-r", "--name-only", tag, "community"], cwd=repo_dir, capture=True)
    return sorted(
        line.strip()
        for line in tree.splitlines()
        if OWNED_PROTO_RE.fullmatch(line.strip()) and "/target/" not in line
    )


def repo_path_to_import_path(repo_path: str) -> str:
    marker = "/src/main/protobuf/"
    if marker not in repo_path:
        raise ValueError(f"Unable to derive import path from '{repo_path}'")
    return repo_path.split(marker, 1)[1]


def descriptor_image_path(cache_dir: Path, version: str) -> Path:
    return cache_dir / "descriptor-images" / version / DESCRIPTOR_IMAGE_NAME


def materialize_descriptor_image(
    repo_dir: Path,
    *,
    tag: str,
    output_path: Path,
    force_refresh: bool,
) -> bool:
    if output_path.exists() and not force_refresh:
        return True
    image_bytes = git_try_bytes(["show", f"{tag}:{DESCRIPTOR_IMAGE_NAME}"], cwd=repo_dir)
    if image_bytes is None:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)
    return True


def docs_json_page_ref(path: Path, docs_json_path: Path) -> str:
    relative = path.resolve().relative_to(docs_json_path.resolve().parent)
    if relative.suffix != ".mdx":
        raise ValueError(f"Expected MDX file under docs root, got: {path}")
    return relative.with_suffix("").as_posix()


def page_title(path: Path) -> str:
    match = TITLE_RE.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"Unable to find title frontmatter in {path}")
    return match.group("title")


def page_count(path: Path, pattern: re.Pattern[str], *, label: str) -> int:
    match = pattern.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"Unable to find {label} count in {path}")
    return int(match.group("count"))


def package_group(package_name: str, *, has_services: bool) -> str:
    if not has_services:
        return "Schema Packages"
    if package_name.startswith("com.daml.ledger.api.v2"):
        return "Ledger API"
    if ".participant." in package_name:
        return "Participant Administration"
    if "sequencer" in package_name:
        return "Sequencer"
    if "mediator" in package_name:
        return "Mediator"
    if package_name.startswith(
        (
            "com.digitalasset.canton.admin.health",
            "com.digitalasset.canton.connection",
            "com.digitalasset.canton.crypto",
            "com.digitalasset.canton.time",
            "com.digitalasset.canton.topology",
        )
    ):
        return "Shared Administration"
    return "Other APIs"


def package_group_sort_key(package_name: str, *, has_services: bool) -> tuple[int, str]:
    label = package_group(package_name, has_services=has_services)
    return (PACKAGE_GROUP_ORDER.index(label), package_name)


def grouped_package_nav_pages(*, docs_json_path: Path, package_dir: Path) -> list[dict[str, Any]]:
    package_entries: list[dict[str, Any]] = []
    for page_path in sorted(package_dir.glob("*.mdx")):
        package_name = page_title(page_path)
        service_count = page_count(page_path, CURRENT_SERVICES_RE, label="services")
        endpoint_count = page_count(page_path, CURRENT_ENDPOINTS_RE, label="endpoints")
        package_entries.append(
            {
                "package": package_name,
                "page_ref": docs_json_page_ref(page_path, docs_json_path),
                "has_services": bool(service_count or endpoint_count),
            }
        )

    package_entries.sort(
        key=lambda entry: package_group_sort_key(
            entry["package"],
            has_services=entry["has_services"],
        )
    )

    grouped_pages: dict[str, list[str]] = {label: [] for label in PACKAGE_GROUP_ORDER}
    for entry in package_entries:
        grouped_pages[package_group(entry["package"], has_services=entry["has_services"])].append(entry["page_ref"])

    return [
        {"group": label, "pages": grouped_pages[label]}
        for label in PACKAGE_GROUP_ORDER
        if grouped_pages[label]
    ]


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
    package_dir: Path,
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
    target_pages.append(
        {
            "group": GROUP_LABEL,
            "pages": [
                page_ref,
                *grouped_package_nav_pages(docs_json_path=docs_json_path, package_dir=package_dir),
            ],
        }
    )
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
        "source": source_config.get("source") or "Canton protobuf descriptor snapshots from local git tags",
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
    repo_config = source_config.get("repo") if isinstance(source_config.get("repo"), dict) else {}
    remote = repo_config.get("remote")
    if not isinstance(remote, str) or not remote:
        raise ValueError("Source config must define repo.remote")

    include_versions = set(args.version) if args.version else None
    min_version = args.min_version or source_config.get("min_version") or "0.0.0"
    if not isinstance(min_version, str):
        raise ValueError("min_version must be a string")

    repo_dir = ensure_repo(Path(args.repo_dir).resolve(), remote=remote, fetch=not args.skip_fetch)
    selected_tags = stable_tags(repo_dir, min_version=min_version, include_versions=include_versions)
    if not selected_tags:
        raise ValueError("No stable Canton tags selected")

    cache_dir = Path(args.cache_dir).resolve()
    releases: list[dict[str, Any]] = []
    for version, tag in selected_tags:
        proto_paths = list_owned_proto_paths(repo_dir, tag)
        if not proto_paths:
            print(f"Skipping {tag}: no owned protobuf files found")
            continue
        image_path = descriptor_image_path(cache_dir, version)
        if not materialize_descriptor_image(
            repo_dir,
            tag=tag,
            output_path=image_path,
            force_refresh=args.force_refresh,
        ):
            print(f"Skipping {tag}: missing {DESCRIPTOR_IMAGE_NAME}")
            continue
        releases.append(
            {
                "version": version,
                "tag": tag,
                "date": release_date(repo_dir, tag),
                "descriptor_image_path": str(image_path.resolve()),
                "import_to_repo_path": {
                    repo_path_to_import_path(repo_path): repo_path
                    for repo_path in proto_paths
                },
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
            version_filter = "selected stable Canton release tags"
        else:
            version_filter = f"stable Canton release tags >= {min_version}"

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
        package_dir=Path(args.output_dir).resolve() / "packages",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
