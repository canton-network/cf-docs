#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
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


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import splice_openapi_release_bundles


DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "splice-daml-api" / "source-artifacts.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "splice-daml-api"
DEFAULT_MANIFEST_ROOT = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "splice-daml-api"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "docs-main" / "reference" / "splice-daml-api"
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
        description="Generate the Splice Daml API reference from published splice-node release-bundle DARs."
    )
    parser.add_argument("--source-config", default=str(DEFAULT_SOURCE_CONFIG))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--manifest-root", default=str(DEFAULT_MANIFEST_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--docs-json", default=str(DEFAULT_DOCS_JSON))
    parser.add_argument("--nav-dropdown", default="API Reference")
    parser.add_argument("--family", action="append", help="Family name to generate. Repeat to limit generation.")
    parser.add_argument("--version", action="append", help="Release version to include. Repeat to limit generation.")
    parser.add_argument("--publish-version", help="Release version whose docs should be published.")
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


def configured_sections(source_config: dict[str, Any]) -> list[dict[str, Any]]:
    sections = source_config.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("Source config must define a non-empty `sections` list")
    output: list[dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("Each section must be an object")
        group = section.get("group")
        description = section.get("description")
        families = section.get("families")
        if not isinstance(group, str) or not group:
            raise ValueError("Each section must define a non-empty string `group`")
        if description is not None and not isinstance(description, str):
            raise ValueError("Section `description` must be a string when present")
        if not isinstance(families, list) or not families or not all(isinstance(item, str) and item for item in families):
            raise ValueError(f"Section {group!r} must define a non-empty string list `families`")
        output.append({"group": group, "description": description or "", "families": families})
    return output


def blocked_live_families(source_config: dict[str, Any]) -> dict[str, str]:
    payload = source_config.get("blocked_live_families") or []
    if not isinstance(payload, list):
        raise ValueError("blocked_live_families must be a list when present")
    blocked: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Each blocked_live_families entry must be an object")
        name = item.get("name")
        reason = item.get("reason")
        if not isinstance(name, str) or not name:
            raise ValueError("Each blocked_live_families entry needs a non-empty `name`")
        if not isinstance(reason, str) or not reason:
            raise ValueError(f"Blocked family {name!r} needs a non-empty `reason`")
        blocked[name] = reason
    return blocked


def configured_families(source_config: dict[str, Any]) -> list[str]:
    sections = configured_sections(source_config)
    families: list[str] = []
    seen: set[str] = set()
    for section in sections:
        for family in section["families"]:
            if family in seen:
                raise ValueError(f"Duplicate family configured: {family}")
            seen.add(family)
            families.append(family)
    return families


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
            filename = Path(member.name).name
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
    command = ["daml", "damlc", "docs"]
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
    shutil.rmtree(output_dir, ignore_errors=True)
    route_prefix = docs_route(output_dir / "index.mdx", docs_json_path)
    command = [
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
    ]
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=str(REPO_ROOT), check=True)


def family_group(*, family_dir: Path, docs_json_path: Path) -> dict[str, Any]:
    index_path = family_dir / "index.mdx"
    if not index_path.exists():
        raise FileNotFoundError(f"Missing generated family index: {index_path}")
    index_title = read_mdx_title(index_path)
    page_entries = []
    for page in sorted(family_dir.glob("*.mdx")):
        title = read_mdx_title(page)
        page_entries.append((0 if page.name == "index.mdx" else 1, title.lower(), docs_json_page_ref(page, docs_json_path)))
    page_entries.sort()
    return {
        "title": index_title,
        "route": docs_route(index_path, docs_json_path),
        "group": {
            "group": index_title,
            "pages": [page_ref for _sort, _title, page_ref in page_entries],
        },
    }


def ensure_group_path(items: list[Any], group_path: list[str], *, top_level_insert_after_group: str | None) -> list[Any]:
    current_pages = items
    top_level_items = items
    for depth, label in enumerate(group_path):
        group = next((item for item in current_pages if isinstance(item, dict) and item.get("group") == label), None)
        if group is None:
            group = {"group": label, "pages": []}
            if depth == 0 and top_level_insert_after_group:
                inserted = False
                for index, item in enumerate(top_level_items):
                    if isinstance(item, dict) and item.get("group") == top_level_insert_after_group:
                        top_level_items.insert(index + 1, group)
                        inserted = True
                        break
                if not inserted:
                    top_level_items.append(group)
            else:
                current_pages.append(group)
        pages = group.get("pages")
        if not isinstance(pages, list):
            pages = []
            group["pages"] = pages
        current_pages = pages
    return current_pages


def write_overview_page(
    *,
    output_root: Path,
    docs_json_path: Path,
    overview_title: str,
    publish_version: str,
    sections: list[dict[str, Any]],
    generated_groups: dict[str, dict[str, Any]],
    blocked: dict[str, str],
) -> Path:
    lines = [
        "---",
        f'title: "{overview_title}"',
        'description: "Generated package reference pages for the published Splice Daml API DAR artifacts"',
        "---",
        "",
        (
            "These pages mirror the live `docs.sync.global/app_dev/api/` Daml surface wherever the published "
            f"`{publish_version}_splice-node.tar.gz` bundle provides a corresponding DAR artifact."
        ),
        "",
        "## Coverage",
        f"- Generated family pages from published DARs: {len(generated_groups)}",
        f"- Live families blocked by missing release DARs: {len(blocked)}",
        "",
        "## Reference",
    ]

    for section in sections:
        lines.append(f"### {section['group']}")
        if section["description"]:
            lines.append(section["description"])
        lines.append("")
        for family in section["families"]:
            group = generated_groups.get(family)
            if group is None:
                continue
            lines.append(f"- [{group['title']}]({group['route']})")
        lines.append("")

    if blocked:
        lines.extend(["## Artifact gaps", ""])
        for family, reason in blocked.items():
            live_url = f"https://docs.sync.global/app_dev/api/{family}/index.html"
            lines.append(f"- `{family}`: {reason} Live page: {live_url}")
        lines.append("")

    output_root.mkdir(parents=True, exist_ok=True)
    overview_path = output_root / "index.mdx"
    overview_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return overview_path


def update_docs_navigation(
    *,
    docs_json_path: Path,
    dropdown_label: str,
    parent_groups: list[str],
    top_level_insert_after_group: str | None,
    nav_group_label: str,
    output_root: Path,
    sections: list[dict[str, Any]],
    generated_groups: dict[str, dict[str, Any]],
) -> None:
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

    target_pages = ensure_group_path(
        pages,
        parent_groups,
        top_level_insert_after_group=top_level_insert_after_group,
    )
    target_pages[:] = [
        item
        for item in target_pages
        if not (isinstance(item, dict) and item.get("group") == nav_group_label)
    ]

    group_pages: list[Any] = [docs_json_page_ref(output_root / "index.mdx", docs_json_path)]
    for section in sections:
        section_groups = [
            generated_groups[family]["group"]
            for family in section["families"]
            if family in generated_groups
        ]
        if section_groups:
            group_pages.append({"group": section["group"], "pages": section_groups})

    target_pages.append({"group": nav_group_label, "pages": group_pages})
    docs_json_path.write_text(json.dumps(docs, indent=2) + "\n", encoding="utf-8")
    print(f"Updated docs navigation: {docs_json_path}")


def main() -> int:
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    sections = configured_sections(source_config)
    blocked = blocked_live_families(source_config)
    configured = configured_families(source_config)
    include_families = set(args.family or configured)
    unknown_families = include_families.difference(configured)
    if unknown_families:
        raise ValueError(f"Unknown family selection: {sorted(unknown_families)}")

    releases = splice_openapi_release_bundles.selected_releases(
        source_config=source_config,
        include_versions=set(args.version) if args.version else None,
    )
    publish_version = args.publish_version or str(source_config.get("publish_version") or releases[-1]["version"])
    release_by_version = {release["version"]: release for release in releases}
    if publish_version not in release_by_version:
        raise ValueError(f"Publish version {publish_version!r} was not selected")
    publish_release = release_by_version[publish_version]

    cache_dir = Path(args.cache_dir).resolve()
    manifest_root = Path(args.manifest_root).resolve()
    output_root = Path(args.output_root).resolve()
    docs_json_path = Path(args.docs_json).resolve()

    publish_archive = splice_openapi_release_bundles.ensure_archive(
        cache_dir=cache_dir,
        release=publish_release,
        force_refresh=args.force_refresh,
    )
    live_families = live_families_from_archive(publish_archive)
    covered_families = set(configured).union(blocked)
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
    for family in configured:
        if family not in publish_dars:
            raise ValueError(f"Configured family {family!r} has no DAR in publish release {publish_version}")
    for family in blocked:
        if family in publish_dars:
            raise ValueError(f"Blocked family {family!r} unexpectedly has a DAR in publish release {publish_version}")

    package_info_by_version: dict[str, dict[str, PackageInfo]] = {}
    package_info_by_id: dict[str, dict[str, PackageInfo]] = {}
    for release in releases:
        archive = splice_openapi_release_bundles.ensure_archive(
            cache_dir=cache_dir,
            release=release,
            force_refresh=args.force_refresh,
        )
        dar_members = dar_members_from_archive(archive)
        family_infos: dict[str, PackageInfo] = {}
        id_index: dict[str, PackageInfo] = {}
        for family in configured:
            member_name = dar_members.get(family)
            if member_name is None:
                continue
            extract_dir = extract_dar(
                archive_path=archive,
                dar_member_name=member_name,
                output_dir=cache_dir / "extracted" / release["version"] / family,
                force_refresh=args.force_refresh,
            )
            info = package_info(family=family, extract_dir=extract_dir)
            family_infos[family] = info
            id_index[info.package_id] = info
        package_info_by_version[release["version"]] = family_infos
        package_info_by_id[release["version"]] = id_index

    generated_groups: dict[str, dict[str, Any]] = {}
    for family in configured:
        if family not in include_families:
            continue

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
                force_regenerate=args.force_regenerate,
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
            source_name=args.source_name,
            publish_version=publish_version,
            versions=manifest_versions,
        )
        family_output_dir = output_root / family
        run_x2mdx(
            manifest_path=manifest_path,
            output_dir=family_output_dir,
            publish_version=publish_version,
            overview_title=f"{family} docs",
            source_name=args.source_name,
            version_filter=args.version_filter,
            docs_json_path=docs_json_path,
        )
        generated_groups[family] = family_group(family_dir=family_output_dir, docs_json_path=docs_json_path)

    overview_path = write_overview_page(
        output_root=output_root,
        docs_json_path=docs_json_path,
        overview_title=str(source_config.get("overview_title") or "Splice Daml APIs"),
        publish_version=publish_version,
        sections=sections,
        generated_groups=generated_groups,
        blocked=blocked,
    )
    print(f"Wrote overview page: {overview_path}")

    update_docs_navigation(
        docs_json_path=docs_json_path,
        dropdown_label=args.nav_dropdown,
        parent_groups=list(source_config.get("nav_parent_groups") or []),
        top_level_insert_after_group=source_config.get("top_level_insert_after_group")
        if isinstance(source_config.get("top_level_insert_after_group"), str)
        else None,
        nav_group_label=str(source_config.get("nav_group_label") or "Daml APIs"),
        output_root=output_root,
        sections=sections,
        generated_groups=generated_groups,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
