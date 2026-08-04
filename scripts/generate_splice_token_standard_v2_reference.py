#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from docs_env import ensure_repo_direnv, repo_direnv_command

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SOURCE_CONFIG = (
    REPO_ROOT
    / "config"
    / "x2mdx"
    / "splice-token-standard-v2"
    / "source-artifacts.json"
)
DEFAULT_CACHE_DIR = (
    Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser()
    / "x2mdx"
    / "splice-token-standard-v2"
)
DEFAULT_MANIFEST_ROOT = (
    REPO_ROOT / ".internal" / "generated" / "x2mdx" / "splice-token-standard-v2"
)
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT / "docs-main" / "sdks-tools" / "api-reference" / "splice-daml"
)
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"


@dataclass(frozen=True)
class PackageInfo:
    family: str
    package_name: str
    package_id: str
    package_root: Path
    exposed_modules: list[str]
    depends: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Token Standard v2 Daml package reference pages through the x2mdx daml-json renderer."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--manifest-root", default=str(DEFAULT_MANIFEST_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument(
        "--nav-product",
        help="docs.json navigation product to update. Defaults to manifest nav_product.",
    )
    parser.add_argument(
        "--family",
        action="append",
        help="Package family to generate. Repeat to limit generation.",
    )
    parser.add_argument(
        "--version",
        action="append",
        help="Release version to include. Repeat to limit generation.",
    )
    parser.add_argument(
        "--publish-version", help="Release version whose pages should be published."
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Re-download and re-extract release bundles.",
    )
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="Regenerate Daml docs JSON and MDX output.",
    )
    parser.add_argument(
        "--source-name",
        default="Canton Network Token Standard v2 DARs from canton-network/splice",
        help="Source label embedded in generated content.",
    )
    parser.add_argument(
        "--version-filter",
        default="configured Token Standard v2 DAR package version",
        help="Version-filter label embedded in generated content.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def require_string(payload: dict[str, Any], key: str, *, source_path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{source_path} must define non-empty string field '{key}'")
    return value


def require_string_list(
    payload: dict[str, Any], key: str, *, source_path: Path
) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"{source_path} must define string list field '{key}'")
    return list(value)


def docs_json_page_ref(path: Path, docs_json_path: Path) -> str:
    relative = path.resolve().relative_to(docs_json_path.resolve().parent)
    if relative.suffix != ".mdx":
        raise ValueError(f"Expected MDX file under docs root, got: {path}")
    return relative.with_suffix("").as_posix()


def docs_route(path: Path, docs_json_path: Path) -> str:
    page_ref = docs_json_page_ref(path, docs_json_path).removesuffix("/index")
    return f"/{page_ref}"


def read_mdx_title(path: Path) -> str:
    in_frontmatter = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "---":
            if in_frontmatter:
                break
            in_frontmatter = True
            continue
        if not in_frontmatter:
            continue
        if line.startswith("title: "):
            return line.split(":", 1)[1].strip().strip('"')
    raise ValueError(f"Missing title frontmatter in {path}")


def dar_family(filename: str, *, package_version: str) -> str:
    suffix = f"-{package_version}.dar"
    if not filename.endswith(suffix):
        raise ValueError(f"DAR filename must end in {suffix!r}: {filename}")
    return filename[: -len(suffix)]


def ensure_dar(
    *,
    repository: str,
    revision: str,
    filename: str,
    cache_dir: Path,
    force_refresh: bool,
) -> Path:
    output_path = cache_dir / "dars" / revision / filename
    if output_path.exists() and not force_refresh:
        return output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://raw.githubusercontent.com/{repository}/{revision}/daml/dars/{filename}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "cf-docs-token-standard-v2-generator"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    if not payload.startswith(b"PK"):
        raise ValueError(f"Downloaded DAR is not a zip archive: {url}")
    output_path.write_bytes(payload)
    print(f"Downloaded DAR: {url}")
    return output_path


def extract_dar(
    *,
    dar_path: Path,
    output_dir: Path,
    force_refresh: bool,
) -> Path:
    if output_dir.exists() and not force_refresh and any(output_dir.rglob("*.daml")):
        return output_dir

    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dar_path) as dar_zip:
        dar_zip.extractall(output_dir)
    return output_dir


def package_info(*, family: str, extract_dir: Path) -> PackageInfo:
    package_root = next(
        (
            path
            for path in sorted(extract_dir.iterdir())
            if path.is_dir() and path.name != "META-INF"
        ),
        None,
    )
    if package_root is None:
        raise FileNotFoundError(
            f"Could not find extracted package root in {extract_dir}"
        )

    conf_path = next((package_root / "data").glob("*.conf"), None)
    if conf_path is None:
        raise FileNotFoundError(f"Missing package conf in {package_root / 'data'}")

    fields: dict[str, str] = {}
    for line in conf_path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()

    package_id = fields.get("id")
    if not package_id:
        raise ValueError(f"Missing package id in {conf_path}")
    package_name = fields.get("name")
    if not package_name:
        raise ValueError(f"Missing package name in {conf_path}")
    exposed_modules = [
        item for item in fields.get("exposed-modules", "").split() if item
    ]
    if not exposed_modules:
        raise ValueError(f"Missing exposed modules in {conf_path}")
    depends = [item for item in fields.get("depends", "").split() if item]
    return PackageInfo(
        family=family,
        package_name=package_name,
        package_id=package_id,
        package_root=package_root,
        exposed_modules=exposed_modules,
        depends=depends,
    )


def module_source_paths(info: PackageInfo) -> list[str]:
    source_paths: list[str] = []
    for module_name in info.exposed_modules:
        relative_path = Path(*module_name.split(".")).with_suffix(".daml")
        source_path = info.package_root / relative_path
        if not source_path.exists():
            raise FileNotFoundError(
                f"Missing source file for module {module_name}: {source_path}"
            )
        source_paths.append(str(relative_path))
    return source_paths


def dependency_include_dirs(
    *,
    info: PackageInfo,
    package_index: dict[str, PackageInfo],
) -> list[Path]:
    include_dirs: list[Path] = []
    seen_ids: set[str] = set()
    package_name_index = {
        package.package_name: package for package in package_index.values()
    }

    def resolve_dependency(package_id: str) -> PackageInfo | None:
        exact = package_index.get(package_id)
        if exact is not None:
            return exact
        candidates = [
            package
            for package_name, package in package_name_index.items()
            if package_id == package_name or package_id.startswith(f"{package_name}-")
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda package: len(package.package_name), reverse=True)
        return candidates[0]

    def visit(package_id: str) -> None:
        if package_id in seen_ids:
            return
        seen_ids.add(package_id)
        dependency = resolve_dependency(package_id)
        if dependency is None:
            return
        include_dirs.append(dependency.package_root)
        for nested in dependency.depends:
            visit(nested)

    for dependency_id in info.depends:
        visit(dependency_id)
    return include_dirs


def repo_tool_command(*args: str) -> list[str]:
    if os.environ.get("DIGITAL_ASSET_DOCS_DIRENV") == "1":
        return list(args)
    return repo_direnv_command(REPO_ROOT, *args)


def generate_daml_json(
    *,
    info: PackageInfo,
    include_dirs: list[Path],
    output_json: Path,
    force_regenerate: bool,
) -> Path:
    if output_json.exists() and not force_regenerate:
        print(f"Using cached Daml docs JSON: {output_json}")
        return output_json

    output_json.parent.mkdir(parents=True, exist_ok=True)
    command = repo_tool_command(
        "dpm",
        "damlc",
        "docs",
        "--ignore-data-deps-visibility",
        "yes",
    )
    for include_dir in include_dirs:
        command.extend(["--include", str(include_dir)])
    command.extend(
        [
            "--include-modules",
            ",".join(info.exposed_modules),
            "--format",
            "json",
            "--output",
            str(output_json),
            *module_source_paths(info),
        ]
    )
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=str(info.package_root), check=True)
    return output_json


def write_manifest(
    *,
    manifest_path: Path,
    source_name: str,
    publish_version: str,
    versions: list[dict[str, str]],
) -> Path:
    manifest = {
        "source": source_name,
        "publish_version": publish_version,
        "versions": versions,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    return manifest_path


def run_x2mdx(
    *,
    manifest_path: Path,
    output_dir: Path,
    publish_version: str,
    overview_title: str,
    source_name: str,
    version_filter: str,
    docs_json_path: Path,
) -> None:
    route_prefix = docs_route(output_dir / "index.mdx", docs_json_path)
    command = repo_tool_command(
        "python3",
        "-m",
        "x2mdx.cli",
        "daml-json",
        "build-api-pages-from-manifest",
        "--manifest",
        str(manifest_path),
        "--output-dir",
        str(output_dir),
        "--publish-version",
        publish_version,
        "--overview-title",
        overview_title,
        "--source-name",
        source_name,
        "--version-filter",
        version_filter,
        "--link-prefix",
        route_prefix,
    )
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=str(REPO_ROOT), check=True)
    index_path = output_dir / "index.mdx"
    index_text = index_path.read_text(encoding="utf-8")
    index_text = index_text.replace(
        "Generated module overview for the Daml Standard Library, built from versioned docs JSON snapshots.",
        f"Generated module overview for {overview_title}, built from the published DAR artifact.",
    )
    index_path.write_text(index_text, encoding="utf-8")


def family_group(*, family_dir: Path, docs_json_path: Path) -> dict[str, Any]:
    index_path = family_dir / "index.mdx"
    if not index_path.exists():
        raise FileNotFoundError(f"Missing generated family index: {index_path}")
    page_entries = []
    for page in sorted(family_dir.glob("*.mdx")):
        title = read_mdx_title(page)
        page_entries.append(
            (
                0 if page.name == "index.mdx" else 1,
                title.lower(),
                docs_json_page_ref(page, docs_json_path),
            )
        )
    page_entries.sort()
    return {
        "group": family_dir.name,
        "pages": [page_ref for _sort, _title, page_ref in page_entries],
    }


def navigation_product_pages(
    docs: dict[str, Any], *, product_label: str, docs_json_path: Path
) -> list[Any]:
    navigation = docs.get("navigation")
    if not isinstance(navigation, dict):
        raise ValueError(f"docs.json navigation must be an object: {docs_json_path}")
    products = navigation.get("products")
    if not isinstance(products, list):
        raise ValueError(
            f"docs.json navigation.products must be a list: {docs_json_path}"
        )
    product = next(
        (
            item
            for item in products
            if isinstance(item, dict) and item.get("product") == product_label
        ),
        None,
    )
    if product is None:
        raise ValueError(f"Product not found in docs.json: {product_label}")
    pages = product.get("pages")
    if isinstance(pages, list):
        return pages
    groups = product.get("groups")
    if isinstance(groups, list):
        return groups
    raise ValueError(f"Product does not expose a pages or groups list: {product_label}")


def ensure_group_path(items: list[Any], group_path: list[str]) -> list[Any]:
    current_pages = items
    for label in group_path:
        group = next(
            (
                item
                for item in current_pages
                if isinstance(item, dict) and item.get("group") == label
            ),
            None,
        )
        if group is None:
            group = {"group": label, "pages": []}
            current_pages.append(group)
        pages = group.get("pages")
        if not isinstance(pages, list):
            pages = []
            group["pages"] = pages
        current_pages = pages
    return current_pages


def replace_group(items: list[Any], group: dict[str, Any]) -> None:
    label = group.get("group")
    if not isinstance(label, str) or not label:
        raise ValueError(f"Expected navigation group label: {group}")
    replacement_index: int | None = None
    filtered: list[Any] = []
    for item in items:
        if isinstance(item, dict) and item.get("group") == label:
            if replacement_index is None:
                replacement_index = len(filtered)
            continue
        filtered.append(item)
    if replacement_index is None:
        filtered.append(group)
    else:
        filtered.insert(replacement_index, group)
    items[:] = filtered


def update_docs_navigation(
    *,
    docs_json_path: Path,
    product_label: str,
    parent_groups: list[str],
    nav_group_label: str,
    output_root: Path,
    family_order: list[str],
) -> None:
    docs = load_json(docs_json_path)
    pages = navigation_product_pages(
        docs, product_label=product_label, docs_json_path=docs_json_path
    )
    target_pages = ensure_group_path(pages, parent_groups)
    generated_groups = [
        family_group(family_dir=output_root / family, docs_json_path=docs_json_path)
        for family in family_order
        if (output_root / family / "index.mdx").exists()
    ]
    if not generated_groups:
        raise FileNotFoundError(
            f"No Splice Daml package output directories found under {output_root}"
        )
    existing_group = next(
        (
            item
            for item in target_pages
            if isinstance(item, dict) and item.get("group") == nav_group_label
        ),
        None,
    )
    existing_pages = (
        existing_group.get("pages") if isinstance(existing_group, dict) else []
    )
    if not isinstance(existing_pages, list):
        existing_pages = []
    generated_by_label = {str(group["group"]): group for group in generated_groups}
    merged_groups: list[Any] = []
    for item in existing_pages:
        label = item.get("group") if isinstance(item, dict) else None
        if isinstance(label, str) and label in generated_by_label:
            merged_groups.append(generated_by_label.pop(label))
        else:
            merged_groups.append(item)
    merged_groups.extend(generated_by_label.values())
    group_items = [
        item
        for item in merged_groups
        if isinstance(item, dict) and isinstance(item.get("group"), str)
    ]
    other_items = [item for item in merged_groups if item not in group_items]
    group_items.sort(key=lambda item: str(item["group"]).lower())
    replace_group(
        target_pages, {"group": nav_group_label, "pages": [*other_items, *group_items]}
    )
    docs_json_path.write_text(json.dumps(docs, indent=2) + "\n", encoding="utf-8")
    print(f"Updated docs navigation: {docs_json_path}")


def render_reference(
    *,
    source_config_path: Path,
    cache_dir: Path,
    manifest_root: Path,
    output_root: Path,
    docs_json_path: Path,
    nav_product: str | None,
    include_families: set[str] | None,
    include_versions: set[str] | None,
    publish_version_override: str | None,
    source_name: str,
    version_filter: str,
    force_refresh: bool,
    force_regenerate: bool,
) -> None:
    source_config = load_json(source_config_path)
    repository = require_string(
        source_config, "repository", source_path=source_config_path
    )
    revision = require_string(source_config, "revision", source_path=source_config_path)
    configured_version = require_string(
        source_config, "publish_version", source_path=source_config_path
    )
    published_dars = require_string_list(
        source_config, "published_dars", source_path=source_config_path
    )
    supporting_dars = require_string_list(
        source_config, "supporting_dars", source_path=source_config_path
    )
    if include_versions is not None and configured_version not in include_versions:
        raise ValueError(
            f"Configured package version {configured_version!r} was not selected"
        )
    publish_version = publish_version_override or configured_version
    if publish_version != configured_version:
        raise ValueError(
            f"Publish version {publish_version!r} does not match configured DAR version {configured_version!r}"
        )

    families = [
        dar_family(filename, package_version=configured_version)
        for filename in published_dars
    ]
    if len(families) != len(set(families)):
        raise ValueError("Published DARs must map to unique package families")
    selected_families = [
        family
        for family in families
        if include_families is None or family in include_families
    ]
    unknown_families = (include_families or set()).difference(families)
    if unknown_families:
        raise ValueError(f"Unknown family selection: {sorted(unknown_families)}")
    if not selected_families:
        raise ValueError("No Token Standard v2 families selected for generation")

    family_infos: dict[str, PackageInfo] = {}
    id_index: dict[str, PackageInfo] = {}
    for filename in [*published_dars, *supporting_dars]:
        family = dar_family(filename, package_version=configured_version)
        dar_path = ensure_dar(
            repository=repository,
            revision=revision,
            filename=filename,
            cache_dir=cache_dir,
            force_refresh=force_refresh,
        )
        extract_dir = extract_dar(
            dar_path=dar_path,
            output_dir=cache_dir / "extracted" / revision / family,
            force_refresh=force_refresh,
        )
        info = package_info(family=family, extract_dir=extract_dir)
        family_infos[family] = info
        id_index[info.package_id] = info

    for family in selected_families:
        info = family_infos[family]
        output_json = generate_daml_json(
            info=info,
            include_dirs=dependency_include_dirs(info=info, package_index=id_index),
            output_json=cache_dir / "json" / revision / f"{family}.json",
            force_regenerate=force_regenerate,
        )

        manifest_path = write_manifest(
            manifest_path=manifest_root / family / "manifest.json",
            source_name=source_name,
            publish_version=publish_version,
            versions=[
                {"version": publish_version, "json_path": str(output_json.resolve())}
            ],
        )
        run_x2mdx(
            manifest_path=manifest_path,
            output_dir=output_root / family,
            publish_version=publish_version,
            overview_title=family,
            source_name=source_name,
            version_filter=version_filter,
            docs_json_path=docs_json_path,
        )

    update_docs_navigation(
        docs_json_path=docs_json_path,
        product_label=nav_product
        or require_string(source_config, "nav_product", source_path=source_config_path),
        parent_groups=require_string_list(
            source_config, "nav_parent_groups", source_path=source_config_path
        ),
        nav_group_label=require_string(
            source_config, "nav_group_label", source_path=source_config_path
        ),
        output_root=output_root,
        family_order=families,
    )


def main() -> int:
    ensure_repo_direnv(
        repo_root=REPO_ROOT, script_path=Path(__file__).resolve(), argv=sys.argv[1:]
    )
    args = parse_args()
    render_reference(
        source_config_path=Path(args.source_config).resolve(),
        cache_dir=Path(args.cache_dir).resolve(),
        manifest_root=Path(args.manifest_root).resolve(),
        output_root=Path(args.output_root).resolve(),
        docs_json_path=Path(args.docs_json).resolve(),
        nav_product=args.nav_product,
        include_families=set(args.family) if args.family else None,
        include_versions=set(args.version) if args.version else None,
        publish_version_override=args.publish_version,
        source_name=args.source_name,
        version_filter=args.version_filter,
        force_refresh=args.force_refresh,
        force_regenerate=args.force_regenerate,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
