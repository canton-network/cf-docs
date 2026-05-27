#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
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

from scripts import splice_openapi_release_bundles


DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "splice-daml-reference" / "source-artifacts.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "splice-daml-reference"
DEFAULT_MANIFEST_ROOT = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "splice-daml-reference"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "docs-main" / "sdks-tools" / "api-reference" / "splice-daml"
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
        description="Generate Splice Daml package reference pages through the x2mdx daml-json renderer."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--manifest-root", default=str(DEFAULT_MANIFEST_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--nav-product", help="docs.json navigation product to update. Defaults to manifest nav_product.")
    parser.add_argument("--family", action="append", help="Package family to generate. Repeat to limit generation.")
    parser.add_argument("--version", action="append", help="Release version to include. Repeat to limit generation.")
    parser.add_argument("--publish-version", help="Release version whose pages should be published.")
    parser.add_argument("--force-refresh", action="store_true", help="Re-download and re-extract release bundles.")
    parser.add_argument("--force-regenerate", action="store_true", help="Regenerate Daml docs JSON and MDX output.")
    parser.add_argument(
        "--source-name",
        default="Published Splice Daml docs JSON generated from release DAR artifacts",
        help="Source label embedded in generated content.",
    )
    parser.add_argument(
        "--version-filter",
        default="published splice-node release bundles",
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


def require_string_list(payload: dict[str, Any], key: str, *, source_path: Path) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{source_path} must define string list field '{key}'")
    return list(value)


def configured_families(source_config: dict[str, Any], *, source_path: Path) -> list[str]:
    families = require_string_list(source_config, "families", source_path=source_path)
    blocked = [entry["name"] for entry in blocked_live_families(source_config).values()]
    duplicates = {family for family in families if families.count(family) > 1}
    if duplicates:
        raise ValueError(f"Duplicate configured Splice Daml families: {sorted(duplicates)}")
    if set(families).intersection(blocked):
        raise ValueError("Blocked Splice Daml families must not also be generated families")
    return families


def blocked_live_families(source_config: dict[str, Any]) -> dict[str, dict[str, str]]:
    payload = source_config.get("blocked_live_families") or []
    if not isinstance(payload, list):
        raise ValueError("blocked_live_families must be a list when present")
    blocked: dict[str, dict[str, str]] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Each blocked_live_families entry must be an object")
        name = item.get("name")
        reason = item.get("reason")
        if not isinstance(name, str) or not name:
            raise ValueError("Each blocked_live_families entry needs a non-empty `name`")
        if not isinstance(reason, str) or not reason:
            raise ValueError(f"Blocked family {name!r} needs a non-empty `reason`")
        blocked[name] = {"name": name, "reason": reason}
    return blocked


def docs_json_page_ref(path: Path, docs_json_path: Path) -> str:
    relative = path.resolve().relative_to(docs_json_path.resolve().parent)
    if relative.suffix != ".mdx":
        raise ValueError(f"Expected MDX file under docs root, got: {path}")
    return relative.with_suffix("").as_posix()


def docs_route(path: Path, docs_json_path: Path) -> str:
    page_ref = docs_json_page_ref(path, docs_json_path)
    if page_ref.endswith("/index"):
        page_ref = page_ref[: -len("/index")]
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


def live_families_from_archive(archive_path: Path) -> set[str]:
    pattern = re.compile(r".*/docs/html/app_dev/api/([^/]+)/index\.html$")
    families: set[str] = set()
    with tarfile.open(archive_path, "r:gz") as handle:
        for member in handle.getmembers():
            if not member.isfile():
                continue
            match = pattern.fullmatch(member.name)
            if match:
                families.add(match.group(1))
    if not families:
        raise ValueError(f"No app_dev/api families found in {archive_path}")
    return families


def dar_members_from_archive(archive_path: Path) -> dict[str, str]:
    current_pattern = re.compile(r".*/dars/([^/]+)-current\.dar$")
    fallback_pattern = re.compile(r".*/dars/([^/]+?)-[0-9].*\.dar$")
    members: dict[str, tuple[int, str]] = {}
    with tarfile.open(archive_path, "r:gz") as handle:
        for member in handle.getmembers():
            if not member.isfile() or not member.name.endswith(".dar") or "/dars/" not in member.name:
                continue
            current_match = current_pattern.fullmatch(member.name)
            if current_match:
                family = current_match.group(1)
                priority = 1
            else:
                fallback_match = fallback_pattern.fullmatch(member.name)
                if fallback_match is None:
                    continue
                family = fallback_match.group(1)
                priority = 0
            previous = members.get(family)
            if previous is None or priority > previous[0]:
                members[family] = (priority, member.name)
    return {family: member_name for family, (_priority, member_name) in members.items()}


def extract_dar(
    *,
    archive_path: Path,
    dar_member_name: str,
    output_dir: Path,
    force_refresh: bool,
) -> Path:
    if output_dir.exists() and not force_refresh and any(output_dir.rglob("*.daml")):
        return output_dir

    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="splice-dar-") as temp_dir:
        temp_dar = Path(temp_dir) / "bundle.dar"
        with tarfile.open(archive_path, "r:gz") as handle:
            member = handle.getmember(dar_member_name)
            extracted = handle.extractfile(member)
            if extracted is None:
                raise FileNotFoundError(f"Failed to extract {dar_member_name} from {archive_path}")
            temp_dar.write_bytes(extracted.read())
        with zipfile.ZipFile(temp_dar) as dar_zip:
            dar_zip.extractall(output_dir)
    return output_dir


def package_info(*, family: str, extract_dir: Path) -> PackageInfo:
    package_root = next(
        (path for path in sorted(extract_dir.iterdir()) if path.is_dir() and path.name != "META-INF"),
        None,
    )
    if package_root is None:
        raise FileNotFoundError(f"Could not find extracted package root in {extract_dir}")

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
    exposed_modules = [item for item in fields.get("exposed-modules", "").split() if item]
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
            raise FileNotFoundError(f"Missing source file for module {module_name}: {source_path}")
        source_paths.append(str(relative_path))
    return source_paths


def dependency_include_dirs(
    *,
    info: PackageInfo,
    package_index: dict[str, PackageInfo],
) -> list[Path]:
    include_dirs: list[Path] = []
    seen_ids: set[str] = set()
    package_name_index = {package.package_name: package for package in package_index.values()}

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
    command = repo_direnv_command(
        REPO_ROOT,
        "daml",
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
    command = repo_direnv_command(
        REPO_ROOT,
        "x2mdx",
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


def family_group(*, family_dir: Path, docs_json_path: Path) -> dict[str, Any]:
    index_path = family_dir / "index.mdx"
    if not index_path.exists():
        raise FileNotFoundError(f"Missing generated family index: {index_path}")
    page_entries = []
    for page in sorted(family_dir.glob("*.mdx")):
        title = read_mdx_title(page)
        page_entries.append((0 if page.name == "index.mdx" else 1, title.lower(), docs_json_page_ref(page, docs_json_path)))
    page_entries.sort()
    return {
        "group": family_dir.name,
        "pages": [page_ref for _sort, _title, page_ref in page_entries],
    }


def navigation_product_pages(docs: dict[str, Any], *, product_label: str, docs_json_path: Path) -> list[Any]:
    navigation = docs.get("navigation")
    if not isinstance(navigation, dict):
        raise ValueError(f"docs.json navigation must be an object: {docs_json_path}")
    products = navigation.get("products")
    if not isinstance(products, list):
        raise ValueError(f"docs.json navigation.products must be a list: {docs_json_path}")
    product = next((item for item in products if isinstance(item, dict) and item.get("product") == product_label), None)
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


def remove_group_label(node: Any, label: str) -> None:
    if isinstance(node, list):
        kept: list[Any] = []
        for item in node:
            if isinstance(item, dict) and item.get("group") == label:
                continue
            remove_group_label(item, label)
            kept.append(item)
        node[:] = kept
        return
    if isinstance(node, dict):
        for value in node.values():
            remove_group_label(value, label)


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
    remove_group_label(docs.get("navigation"), nav_group_label)
    pages = navigation_product_pages(docs, product_label=product_label, docs_json_path=docs_json_path)
    target_pages = ensure_group_path(pages, parent_groups)
    groups = [
        family_group(family_dir=output_root / family, docs_json_path=docs_json_path)
        for family in family_order
        if (output_root / family / "index.mdx").exists()
    ]
    if not groups:
        raise FileNotFoundError(f"No Splice Daml package output directories found under {output_root}")
    replace_group(target_pages, {"group": nav_group_label, "pages": groups})
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
    families = configured_families(source_config, source_path=source_config_path)
    blocked = blocked_live_families(source_config)
    selected_families = [family for family in families if include_families is None or family in include_families]
    unknown_families = (include_families or set()).difference(families).difference(blocked)
    if unknown_families:
        raise ValueError(f"Unknown family selection: {sorted(unknown_families)}")
    if not selected_families:
        raise ValueError("No Splice Daml families selected for generation")

    releases = splice_openapi_release_bundles.selected_releases(
        source_config=source_config,
        include_versions=include_versions,
    )
    publish_version = publish_version_override or str(source_config.get("publish_version") or releases[-1]["version"])
    release_by_version = {release["version"]: release for release in releases}
    if publish_version not in release_by_version:
        raise ValueError(f"Publish version {publish_version!r} was not selected")
    publish_release = release_by_version[publish_version]

    publish_archive = splice_openapi_release_bundles.ensure_archive(
        cache_dir=cache_dir,
        release=publish_release,
        force_refresh=force_refresh,
    )
    live_families = live_families_from_archive(publish_archive)
    covered_families = set(families).union(blocked)
    missing_live = sorted(live_families.difference(covered_families))
    extra_covered = sorted(covered_families.difference(live_families))
    if missing_live or extra_covered:
        problems = []
        if missing_live:
            problems.append(f"uncovered live families: {missing_live}")
        if extra_covered:
            problems.append(f"configured families not present on live docs surface: {extra_covered}")
        raise ValueError("; ".join(problems))

    publish_dars = dar_members_from_archive(publish_archive)
    for family in families:
        if family not in publish_dars:
            raise ValueError(f"Configured family {family!r} has no DAR in publish release {publish_version}")

    package_info_by_version: dict[str, dict[str, PackageInfo]] = {}
    package_info_by_id: dict[str, dict[str, PackageInfo]] = {}
    for release in releases:
        archive = splice_openapi_release_bundles.ensure_archive(
            cache_dir=cache_dir,
            release=release,
            force_refresh=force_refresh,
        )
        dar_members = dar_members_from_archive(archive)
        family_infos: dict[str, PackageInfo] = {}
        id_index: dict[str, PackageInfo] = {}
        for family in families:
            member_name = dar_members.get(family)
            if member_name is None:
                continue
            extract_dir = extract_dar(
                archive_path=archive,
                dar_member_name=member_name,
                output_dir=cache_dir / "extracted" / release["version"] / family,
                force_refresh=force_refresh,
            )
            info = package_info(family=family, extract_dir=extract_dir)
            family_infos[family] = info
            id_index[info.package_id] = info
        package_info_by_version[release["version"]] = family_infos
        package_info_by_id[release["version"]] = id_index

    for family in selected_families:
        manifest_versions: list[dict[str, str]] = []
        for release in releases:
            info = package_info_by_version[release["version"]].get(family)
            if info is None:
                continue
            output_json = generate_daml_json(
                info=info,
                include_dirs=dependency_include_dirs(
                    info=info,
                    package_index=package_info_by_id[release["version"]],
                ),
                output_json=cache_dir / "json" / release["version"] / f"{family}.json",
                force_regenerate=force_regenerate,
            )
            manifest_versions.append(
                {
                    "version": release["version"],
                    "json_path": str(output_json.resolve()),
                }
            )

        if not manifest_versions:
            raise ValueError(f"No generated JSON versions available for {family}")

        manifest_path = write_manifest(
            manifest_path=manifest_root / family / "manifest.json",
            source_name=source_name,
            publish_version=publish_version,
            versions=manifest_versions,
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

    family_order = [*families, *blocked.keys()]
    update_docs_navigation(
        docs_json_path=docs_json_path,
        product_label=nav_product or require_string(source_config, "nav_product", source_path=source_config_path),
        parent_groups=require_string_list(source_config, "nav_parent_groups", source_path=source_config_path),
        nav_group_label=require_string(source_config, "nav_group_label", source_path=source_config_path),
        output_root=output_root,
        family_order=family_order,
    )


def main() -> int:
    ensure_repo_direnv(repo_root=REPO_ROOT, script_path=Path(__file__).resolve(), argv=sys.argv[1:])
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
