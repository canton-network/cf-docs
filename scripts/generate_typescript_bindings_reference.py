#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

from docs_env import ensure_repo_direnv, repo_direnv_command

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "x2mdx"
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "typescript-bindings" / "source-artifacts.json"
DEFAULT_CACHE_DIR = DEFAULT_CACHE_ROOT / "typescript-bindings"
DEFAULT_MANIFEST = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "typescript-bindings" / "manifest.json"
DEFAULT_TYPEDOC_DIR = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "typescript-bindings" / "typedoc"
DEFAULT_OUTPUT_FILE = REPO_ROOT / "docs-main" / "reference" / "typescript.mdx"
LEGACY_OUTPUT_FILE = REPO_ROOT / "docs-main" / "sdks-tools" / "language-bindings" / "typescript.mdx"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
DEFAULT_NAV_GROUP = "TypeScript"
LEGACY_NAV_GROUPS = ("Daml TypeScript Bindings",)


def nav_group_labels(group_label: str) -> set[str]:
    return {group_label, *LEGACY_NAV_GROUPS}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the TypeScript bindings reference from published @daml/types npm tarballs via local TypeDoc JSON."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--typedoc-dir", default=str(DEFAULT_TYPEDOC_DIR))
    parser.add_argument("--manifest-out", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-file", default=str(DEFAULT_OUTPUT_FILE))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--nav-dropdown", default="API Reference")
    parser.add_argument("--nav-group", default=DEFAULT_NAV_GROUP)
    parser.add_argument("--version", action="append", help="Version to include. Repeat to limit generation.")
    parser.add_argument("--publish-version", help="Version whose TypeScript surface should be published.")
    parser.add_argument("--force-regenerate", action="store_true")
    parser.add_argument(
        "--source-name",
        default="Published @daml/types npm tarballs rendered to local TypeDoc JSON",
        help="Source label embedded in generated content.",
    )
    parser.add_argument(
        "--version-filter",
        default="configured @daml/types npm versions",
        help="Version-filter label embedded in generated content.",
    )
    parser.add_argument(
        "--page-title",
        default="Details and history",
        help="Title to use for the generated page.",
    )
    parser.add_argument(
        "--page-description",
        default="TypeScript and JavaScript language bindings for Canton.",
        help="Description to use for the generated page.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def docs_json_page_ref(path: Path, docs_json_path: Path) -> str:
    relative = path.resolve().relative_to(docs_json_path.resolve().parent)
    if relative.suffix != ".mdx":
        raise ValueError(f"Expected MDX file under docs root, got: {path}")
    return relative.with_suffix("").as_posix()


def prune_nav_items(items: list[Any], *, page_ref: str, group_label: str) -> list[Any]:
    pruned: list[Any] = []
    group_labels = nav_group_labels(group_label)
    for item in items:
        if isinstance(item, str):
            if item != page_ref:
                pruned.append(item)
            continue
        if isinstance(item, dict):
            if item.get("group") in group_labels:
                continue
            updated = dict(item)
            pages = updated.get("pages")
            if isinstance(pages, list):
                updated["pages"] = prune_nav_items(pages, page_ref=page_ref, group_label=group_label)
            pruned.append(updated)
            continue
        pruned.append(item)
    return pruned


def nav_group_index(items: list[Any], *, group_label: str) -> int | None:
    group_labels = nav_group_labels(group_label)
    for index, item in enumerate(items):
        if isinstance(item, dict) and item.get("group") in group_labels:
            return index
    return None


def update_docs_navigation(
    *,
    docs_json_path: Path,
    dropdown_label: str,
    output_file: Path,
    nav_group: str,
) -> Path:
    docs = load_json(docs_json_path)
    dropdowns = docs.get("navigation", {}).get("dropdowns")
    if not isinstance(dropdowns, list):
        raise ValueError(f"docs.json navigation.dropdowns must be a list: {docs_json_path}")
    dropdown = next((item for item in dropdowns if isinstance(item, dict) and item.get("dropdown") == dropdown_label), None)
    if dropdown is None:
        raise ValueError(f"Dropdown not found in docs.json: {dropdown_label}")
    pages = dropdown.get("pages")
    if not isinstance(pages, list):
        raise ValueError(f"Dropdown does not expose a pages list: {dropdown_label}")

    page_ref = docs_json_page_ref(output_file, docs_json_path)
    existing_index = nav_group_index(pages, group_label=nav_group)
    updated_pages = prune_nav_items(pages, page_ref=page_ref, group_label=nav_group)
    nav_item = {"group": nav_group, "pages": [page_ref]}
    if existing_index is None:
        updated_pages.append(nav_item)
    else:
        updated_pages.insert(min(existing_index, len(updated_pages)), nav_item)
    dropdown["pages"] = updated_pages

    docs_json_path.write_text(json.dumps(docs, indent=2) + "\n", encoding="utf-8")
    print(f"Updated docs navigation: {docs_json_path}")
    return docs_json_path


def remove_legacy_output(*, output_file: Path) -> None:
    legacy_output = LEGACY_OUTPUT_FILE.resolve()
    if output_file == legacy_output:
        return
    if legacy_output.exists():
        legacy_output.unlink()
        print(f"Removed legacy output: {legacy_output}")


def run(command: list[str], *, cwd: Path, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    print("Running:", " ".join(command))
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def patch_tsconfig(package_dir: Path) -> None:
    tsconfig_path = package_dir / "tsconfig.json"
    payload = json.loads(tsconfig_path.read_text(encoding="utf-8"))
    compiler_options = payload.setdefault("compilerOptions", {})
    if not isinstance(compiler_options, dict):
        raise ValueError(f"Expected compilerOptions object in {tsconfig_path}")
    compiler_options["ignoreDeprecations"] = "5.0"
    compiler_options["typeRoots"] = ["./node_modules/@types"]
    tsconfig_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def prepare_package(
    *,
    cache_dir: Path,
    package_name: str,
    version: str,
    force_regenerate: bool,
) -> Path:
    version_dir = cache_dir / version
    package_dir = version_dir / "package"
    tarball_path = version_dir / "package.tgz"

    if force_regenerate and version_dir.exists():
        shutil.rmtree(version_dir)

    if package_dir.exists():
        patch_tsconfig(package_dir)
        return package_dir

    version_dir.mkdir(parents=True, exist_ok=True)
    completed = run(
        ["npm", "pack", "--silent", f"{package_name}@{version}"],
        cwd=version_dir,
        capture_output=True,
    )
    tarball_name = completed.stdout.strip().splitlines()[-1].strip()
    packed_tarball = version_dir / tarball_name
    packed_tarball.rename(tarball_path)
    with tarfile.open(tarball_path, "r:gz") as archive:
        archive.extractall(version_dir)
    if not package_dir.exists():
        raise ValueError(f"Expected npm tarball to extract a package directory at {package_dir}")
    patch_tsconfig(package_dir)
    return package_dir


def ensure_package_dependencies(package_dir: Path, *, force_regenerate: bool) -> None:
    node_modules_dir = package_dir / "node_modules"
    if force_regenerate and node_modules_dir.exists():
        shutil.rmtree(node_modules_dir)
    if node_modules_dir.exists():
        print(f"Using cached npm install: {package_dir}")
        return
    run(
        ["npm", "install", "--ignore-scripts", "--no-package-lock", "--silent"],
        cwd=package_dir,
    )


def ensure_typedoc_json(
    *,
    cache_dir: Path,
    typedoc_dir: Path,
    package_name: str,
    typedoc_version: str,
    version: str,
    force_regenerate: bool,
) -> Path:
    output_json = typedoc_dir / version / "typedoc.json"
    if output_json.exists() and not force_regenerate:
        print(f"Using cached TypeDoc JSON: {output_json}")
        return output_json

    package_dir = prepare_package(
        cache_dir=cache_dir,
        package_name=package_name,
        version=version,
        force_regenerate=force_regenerate,
    )
    ensure_package_dependencies(package_dir, force_regenerate=force_regenerate)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "npx",
            "--yes",
            f"typedoc@{typedoc_version}",
            "--json",
            str(output_json),
            "index.d.ts",
        ],
        cwd=package_dir,
    )
    return output_json


def write_manifest(
    *,
    source_config: dict[str, Any],
    manifest_path: Path,
    typedoc_dir: Path,
    versions: list[str],
    publish_version: str,
) -> Path:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": source_config.get("source") or "digital-asset/docs local TypeDoc cache",
        "package_name": source_config.get("package_name") or "@daml/types",
        "publish_version": publish_version,
        "versions": [
            {
                "version": version,
                "json_path": str((typedoc_dir / version / "typedoc.json").resolve()),
            }
            for version in versions
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    return manifest_path


def main() -> int:
    ensure_repo_direnv(repo_root=REPO_ROOT, script_path=Path(__file__).resolve(), argv=sys.argv[1:])
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    configured_versions = source_config.get("versions")
    if not isinstance(configured_versions, list) or not all(isinstance(item, str) for item in configured_versions):
        raise ValueError("Source config must define a string list under `versions`")
    selected_versions = [version for version in configured_versions if not args.version or version in set(args.version)]
    if not selected_versions:
        raise ValueError("No @daml/types versions selected")

    package_name = str(source_config.get("package_name") or "@daml/types")
    typedoc_version = str(source_config.get("typedoc_version") or "0.27.9")
    publish_version = args.publish_version or str(source_config.get("publish_version") or selected_versions[-1])

    cache_dir = Path(args.cache_dir).resolve()
    typedoc_dir = Path(args.typedoc_dir).resolve()
    for version in selected_versions:
        ensure_typedoc_json(
            cache_dir=cache_dir,
            typedoc_dir=typedoc_dir,
            package_name=package_name,
            typedoc_version=typedoc_version,
            version=version,
            force_regenerate=args.force_regenerate,
        )

    manifest_path = write_manifest(
        source_config=source_config,
        manifest_path=Path(args.manifest_out).resolve(),
        typedoc_dir=typedoc_dir,
        versions=selected_versions,
        publish_version=publish_version,
    )

    command = repo_direnv_command(
        REPO_ROOT,
        "x2mdx",
        "typedoc",
        "build-api-pages-from-manifest",
        "--manifest",
        str(manifest_path),
        "--output-file",
        str(Path(args.output_file).resolve()),
        "--publish-version",
        publish_version,
        "--source-name",
        args.source_name,
        "--version-filter",
        args.version_filter,
        "--page-title",
        args.page_title,
        "--page-description",
        args.page_description,
    )
    for version in args.version or []:
        command.extend(["--version", version])
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode != 0:
        return completed.returncode

    remove_legacy_output(output_file=Path(args.output_file).resolve())
    update_docs_navigation(
        docs_json_path=Path(args.docs_json).resolve(),
        dropdown_label=args.nav_dropdown,
        output_file=Path(args.output_file).resolve(),
        nav_group=args.nav_group,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
