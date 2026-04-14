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
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "wallet-gateway-openrpc" / "source-artifacts.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "wallet-gateway-openrpc"
DEFAULT_MANIFEST = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "wallet-gateway-openrpc" / "manifest.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs-main" / "reference" / "wallet-gateway-json-rpc"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
DEFAULT_REPO_DIR = DEFAULT_CACHE_DIR / "repos" / "splice-wallet-kernel"
GROUP_LABEL = "Wallet Gateway JSON-RPC"
SPEC_DIR_NAME = "specs"
DEFAULT_RELEASE_REPO = "hyperledger-labs/splice-wallet-kernel"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Wallet Gateway OpenRPC specs from wallet-gateway-remote releases, write an x2mdx manifest, and render Mintlify pages."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--manifest-out", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--repo-dir", default=str(DEFAULT_REPO_DIR))
    parser.add_argument("--nav-dropdown", default="Reference")
    parser.add_argument("--version", action="append", help="Explicit version to include. Repeat to limit generation.")
    parser.add_argument("--publish-version", help="Version whose spec surface should be published.")
    parser.add_argument("--min-version", help="Minimum wallet-gateway-remote release version to include.")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetching tags from origin before reading selected tag snapshots.")
    parser.add_argument(
        "--source-name",
        default="splice-wallet-kernel Wallet Gateway OpenRPC specs from wallet-gateway-remote releases",
        help="Source label embedded in generated content.",
    )
    parser.add_argument(
        "--version-filter",
        help="Version-filter label embedded in generated content.",
    )
    parser.add_argument(
        "--overview-title",
        default=GROUP_LABEL,
        help="Title to use for the generated overview page.",
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


def gh(args: list[str], *, capture: bool = False) -> str:
    return run(["gh", *args], capture=capture)


def git_try_show(repo_dir: Path, tag: str, source_path: str) -> str | None:
    completed = subprocess.run(
        ["git", "show", f"{tag}:{source_path}"],
        cwd=str(repo_dir),
        check=False,
        text=True,
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


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def stable_release_versions(
    *,
    release_repo: str,
    tag_prefix: str,
    min_version: str,
    include_versions: set[str] | None,
) -> list[str]:
    releases_raw = gh(
        ["release", "list", "-R", release_repo, "--json", "tagName", "--limit", "200"],
        capture=True,
    )
    payload = json.loads(releases_raw)
    if not isinstance(payload, list):
        raise ValueError(f"Expected release list from gh for {release_repo}")
    semver_re = re.compile(rf"^{re.escape(tag_prefix)}(?P<version>\d+\.\d+\.\d+)$")
    selected: list[str] = []
    minimum = version_key(min_version)
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        tag_name = entry.get("tagName")
        if not isinstance(tag_name, str):
            continue
        match = semver_re.fullmatch(tag_name)
        if not match:
            continue
        version = match.group("version")
        if version_key(version) < minimum:
            continue
        if include_versions is not None and version not in include_versions:
            continue
        selected.append(version)
    selected.sort(key=version_key)
    return selected


def docs_json_page_ref(path: Path, docs_json_path: Path) -> str:
    relative = path.resolve().relative_to(docs_json_path.resolve().parent)
    if relative.suffix != ".mdx":
        raise ValueError(f"Expected MDX file under docs root, got: {path}")
    return relative.with_suffix("").as_posix()


def slugify(value: str) -> str:
    import re

    output = value.lower()
    output = re.sub(r"[^a-z0-9]+", "-", output)
    output = re.sub(r"-{2,}", "-", output).strip("-")
    return output


def spec_page_ref(output_dir: Path, docs_json_path: Path, spec_id: str) -> str:
    return docs_json_page_ref(output_dir / SPEC_DIR_NAME / f"{slugify(spec_id)}.mdx", docs_json_path)


def overview_page_ref(output_dir: Path, docs_json_path: Path) -> str:
    return docs_json_page_ref(output_dir / "index.mdx", docs_json_path)


def overview_route_prefix(output_dir: Path, docs_json_path: Path) -> str:
    page_ref = overview_page_ref(output_dir, docs_json_path)
    if page_ref.endswith("/index"):
        return "/" + page_ref[: -len("/index")]
    return "/" + page_ref


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


def update_docs_navigation(
    *,
    docs_json_path: Path,
    dropdown_label: str,
    output_dir: Path,
    spec_entries: list[dict[str, Any]],
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

    refs = {overview_page_ref(output_dir, docs_json_path)}
    refs.update(spec_page_ref(output_dir, docs_json_path, spec["spec_id"]) for spec in spec_entries)
    dropdown["pages"] = prune_nav_items(pages, page_refs=refs, group_labels={GROUP_LABEL})
    dropdown["pages"].append(
        {
            "group": GROUP_LABEL,
            "pages": [
                overview_page_ref(output_dir, docs_json_path),
                *[spec_page_ref(output_dir, docs_json_path, spec["spec_id"]) for spec in spec_entries],
            ],
        }
    )
    docs_json_path.write_text(json.dumps(docs, indent=2) + "\n", encoding="utf-8")
    print(f"Updated docs navigation: {docs_json_path}")


def write_manifest(
    *,
    source_config: dict[str, Any],
    manifest_path: Path,
    cache_dir: Path,
    repo_root: Path,
    versions: list[str],
    publish_version: str,
    spec_entries: list[dict[str, Any]],
) -> Path:
    specs_payload: list[dict[str, Any]] = []
    for spec in spec_entries:
        versions_payload: list[dict[str, Any]] = []
        for version in versions:
            fixture_path = cache_dir / "specs" / version / Path(spec["source_path"]).name
            if not fixture_path.exists():
                continue
            versions_payload.append(
                {
                    "version": version,
                    "source_path": spec["source_path"],
                    "fixture_path": str(fixture_path.resolve().relative_to(repo_root.resolve())),
                }
            )
        if versions_payload:
            specs_payload.append(
                {
                    "spec_id": spec["spec_id"],
                    "display_name": spec["display_name"],
                    "source_path": spec["source_path"],
                    "versions": versions_payload,
                }
            )

    manifest = {
        "source": source_config.get("source") or "splice-wallet-kernel OpenRPC snapshots",
        "publish_version": publish_version,
        "specs": specs_payload,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    return manifest_path


def main() -> int:
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    include_versions = set(args.version) if args.version else None
    remote = str(source_config.get("remote") or "")
    release_repo = str(source_config.get("release_repo") or DEFAULT_RELEASE_REPO)
    tag_prefix = str(source_config.get("tag_prefix") or "")
    min_version = str(args.min_version or source_config.get("min_version") or "0.0.0")
    spec_entries = source_config.get("specs")
    if not remote or not tag_prefix or not release_repo:
        raise ValueError("Source config must define `remote`, `release_repo`, and `tag_prefix`")
    if not isinstance(spec_entries, list) or not all(isinstance(item, dict) for item in spec_entries):
        raise ValueError("Source config must define a `specs` list of objects")

    selected_versions = stable_release_versions(
        release_repo=release_repo,
        tag_prefix=tag_prefix,
        min_version=min_version,
        include_versions=include_versions,
    )
    if not selected_versions:
        raise ValueError("No wallet-gateway-remote OpenRPC releases selected")

    publish_version = args.publish_version or str(source_config.get("publish_version") or selected_versions[-1])
    if publish_version not in selected_versions:
        raise ValueError(f"Publish version '{publish_version}' is not selected")

    cache_dir = Path(args.cache_dir).resolve()
    repo_dir = Path(args.repo_dir).resolve()
    ensure_repo(repo_dir, remote=remote, fetch=not args.skip_fetch)

    for version in selected_versions:
        tag = f"{tag_prefix}{version}"
        for spec in spec_entries:
            source_path = str(spec["source_path"])
            contents = git_try_show(repo_dir, tag, source_path)
            if contents is None:
                raise ValueError(f"Spec '{source_path}' not found at tag '{tag}'")
            target_path = cache_dir / "specs" / version / Path(source_path).name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(contents, encoding="utf-8")

    manifest_path = write_manifest(
        source_config=source_config,
        manifest_path=Path(args.manifest_out).resolve(),
        cache_dir=cache_dir,
        repo_root=REPO_ROOT,
        versions=selected_versions,
        publish_version=publish_version,
        spec_entries=spec_entries,
    )

    fixture_root = REPO_ROOT
    command = [
        "x2mdx",
        "openrpc",
        "build-api-pages-from-manifest",
        "--manifest",
        str(manifest_path),
        "--fixture-root",
        str(fixture_root),
        "--output-dir",
        str(Path(args.output_dir).resolve()),
        "--publish-version",
        publish_version,
        "--overview-title",
        args.overview_title,
        "--link-prefix",
        overview_route_prefix(Path(args.output_dir).resolve(), Path(args.docs_json).resolve()),
        "--source-name",
        args.source_name,
        "--version-filter",
        args.version_filter or f"{tag_prefix} GitHub releases",
    ]
    for version in args.version or []:
        command.extend(["--version", version])
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode != 0:
        return completed.returncode

    update_docs_navigation(
        docs_json_path=Path(args.docs_json).resolve(),
        dropdown_label=args.nav_dropdown,
        output_dir=Path(args.output_dir).resolve(),
        spec_entries=spec_entries,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
