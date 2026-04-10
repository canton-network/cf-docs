#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "ledger-bindings" / "source-artifacts.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "x2mdx" / "ledger-bindings"
DEFAULT_MANIFEST = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "ledger-bindings" / "manifest.json"
DEFAULT_RENDER_ROOT = REPO_ROOT / ".internal" / "generated" / "x2mdx" / "ledger-bindings" / "site"
DEFAULT_OVERVIEW_FILE = REPO_ROOT / "docs-main" / "reference" / "ledger-api-jvm-bindings.mdx"
DEFAULT_DETAILS_DIR = REPO_ROOT / "docs-main" / "reference"
DEFAULT_DOCS_JSON = REPO_ROOT / "docs-main" / "docs.json"
LEGACY_OVERVIEW_FILE = REPO_ROOT / "docs-main" / "appdev" / "reference" / "ledger-bindings-api-lifecycle.mdx"
LEGACY_DETAILS_DIR = REPO_ROOT / "docs-main" / "appdev" / "reference" / "ledger-bindings-api-lifecycle"
LANGUAGE_LABELS = {
    "scala": "Scaladocs",
    "java": "Javadocs",
}
LANGUAGE_ORDER = {
    "scala": 0,
    "java": 1,
}
LANGUAGE_DIRS = {
    "scala": "scala",
    "java": "java",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download configured JVM doc sources, write a local x2mdx manifest, and generate the Ledger bindings reference pages."
    )
    parser.add_argument(
        "--source-config",
        default=str(DEFAULT_SOURCE_CONFIG),
        help="Checked-in source config listing artifacts and versions to download.",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help="Directory used to cache downloaded JVM doc artifacts and generated jars.",
    )
    parser.add_argument(
        "--manifest-out",
        default=str(DEFAULT_MANIFEST),
        help="Path to the generated local x2mdx manifest.",
    )
    parser.add_argument(
        "--overview-file",
        default=str(DEFAULT_OVERVIEW_FILE),
        help="Path to the published hidden overview MDX page.",
    )
    parser.add_argument(
        "--details-dir",
        default=str(DEFAULT_DETAILS_DIR),
        help="Directory for published per-language pages, such as reference/java/... and reference/scala/....",
    )
    parser.add_argument(
        "--docs-json",
        default=str(DEFAULT_DOCS_JSON),
        help="Path to the Mintlify docs.json file to update.",
    )
    parser.add_argument(
        "--nav-dropdown",
        default="Reference",
        help="Top-level Mintlify dropdown to update with the generated JVM bindings section.",
    )
    parser.add_argument(
        "--nav-group",
        action="append",
        help="Mintlify group path to update. Repeat for nested groups.",
    )
    parser.add_argument(
        "--version",
        action="append",
        help="Artifact version to include. Repeat to limit generation to a subset of configured versions.",
    )
    parser.add_argument(
        "--repo-base",
        help="Override the Maven repository base URL from the checked-in source config.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download source artifacts even if they already exist in the local cache.",
    )
    parser.add_argument(
        "--source-name",
        default="Published JVM docs snapshots",
        help="Source label embedded in generated content.",
    )
    parser.add_argument(
        "--overview-title",
        default="Ledger API JVM Bindings",
        help="Title to use for the generated overview page and parent Mintlify nav group.",
    )
    parser.add_argument(
        "--version-filter",
        default="configured bindings artifact versions",
        help="Version-filter label embedded in generated content.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def slugify(value: str) -> str:
    out = value.lower()
    out = re.sub(r"[^a-z0-9]+", "-", out)
    return re.sub(r"-{2,}", "-", out).strip("-")


def docs_json_page_ref(path: Path, docs_json_path: Path) -> str:
    relative = path.resolve().relative_to(docs_json_path.resolve().parent)
    if relative.suffix != ".mdx":
        raise ValueError(f"Expected MDX file under docs root, got: {path}")
    return relative.with_suffix("").as_posix()


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
        group = next(
            (item for item in current_pages if isinstance(item, dict) and item.get("group") == label),
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


def build_jvm_nav_group(
    *,
    publish_root: Path,
    docs_json_path: Path,
    group_label: str,
) -> tuple[dict[str, Any], set[str]]:
    language_pages: dict[str, list[tuple[str, str]]] = defaultdict(list)
    generated_refs: set[str] = set()

    for language, directory_name in LANGUAGE_DIRS.items():
        language_dir = publish_root / directory_name
        if not language_dir.exists():
            continue
        artifact_index = language_dir / "index.mdx"
        if artifact_index.exists():
            generated_refs.add(docs_json_page_ref(artifact_index, docs_json_path))
        for package_page in sorted(language_dir.glob("*.mdx")):
            if package_page.name == "index.mdx":
                continue
            page_ref = docs_json_page_ref(package_page, docs_json_path)
            language_pages[language].append((read_mdx_title(package_page), page_ref))
            generated_refs.add(page_ref)

    language_groups: list[tuple[int, str, dict[str, Any]]] = []
    for language, page_entries in language_pages.items():
        if not page_entries:
            continue
        page_entries.sort(key=lambda item: (item[0].lower(), item[0]))
        label = LANGUAGE_LABELS.get(language, language.title())
        language_groups.append(
            (
                LANGUAGE_ORDER.get(language, 99),
                label,
                {
                    "group": label,
                    "pages": [page_ref for _, page_ref in page_entries],
                },
            )
        )

    language_groups.sort(key=lambda item: (item[0], item[1]))
    return (
        {
            "group": group_label,
            "pages": [group for _, _, group in language_groups],
        },
        generated_refs,
    )


def update_docs_navigation(
    *,
    docs_json_path: Path,
    dropdown_label: str,
    parent_groups: list[str],
    group_label: str,
    overview_file: Path,
    publish_root: Path,
) -> Path:
    docs = load_json(docs_json_path)
    navigation = docs.get("navigation")
    if not isinstance(navigation, dict):
        raise ValueError(f"docs.json missing navigation object: {docs_json_path}")
    dropdowns = navigation.get("dropdowns")
    if not isinstance(dropdowns, list):
        raise ValueError(f"docs.json navigation.dropdowns must be a list: {docs_json_path}")

    dropdown = next(
        (item for item in dropdowns if isinstance(item, dict) and item.get("dropdown") == dropdown_label),
        None,
    )
    if dropdown is None:
        raise ValueError(f"Dropdown not found in docs.json: {dropdown_label}")

    pages = dropdown.get("pages")
    if not isinstance(pages, list):
        raise ValueError(f"Dropdown does not expose a pages list: {dropdown_label}")

    jvm_group, generated_refs = build_jvm_nav_group(
        publish_root=publish_root,
        docs_json_path=docs_json_path,
        group_label=group_label,
    )
    generated_refs.add(docs_json_page_ref(overview_file, docs_json_path))
    dropdown["pages"] = prune_nav_items(
        pages,
        page_refs=generated_refs,
        group_labels={group_label},
    )
    target_pages = ensure_group_path(dropdown["pages"], parent_groups)
    target_pages.append(jvm_group)

    docs_json_path.write_text(json.dumps(docs, indent=2) + "\n", encoding="utf-8")
    print(f"Updated docs navigation: {docs_json_path}")
    return docs_json_path


def maven_javadoc_url(repo_base: str, group: str, artifact: str, version: str) -> str:
    group_path = group.replace(".", "/")
    file_name = f"{artifact}-{version}-javadoc.jar"
    return f"{repo_base.rstrip('/')}/{group_path}/{artifact}/{version}/{file_name}"


def download_file(url: str, target: Path, *, force: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        print(f"Using cached artifact: {target}")
        return

    print(f"Downloading: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "digital-asset-docs-x2mdx/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            target.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while downloading {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while downloading {url}: {exc}") from exc


def normalize_archive_member_name(name: str) -> str:
    parts = [part for part in Path(name).parts if part not in {"", "."}]
    return Path(*parts).as_posix() if parts else ""


def repackage_tarball_as_jar(source_tarball: Path, target_jar: Path) -> None:
    target_jar.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(source_tarball, "r:gz") as tar, zipfile.ZipFile(
        target_jar,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            arcname = normalize_archive_member_name(member.name)
            if not arcname:
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            with extracted:
                archive.writestr(arcname, extracted.read())


def resolve_cached_jar(
    *,
    repo_base: str,
    cache_dir: Path,
    group: str,
    artifact: str,
    version: str,
    source_kind: str,
    url_template: str | None,
    force_download: bool,
) -> Path:
    if source_kind == "maven-javadoc-jar":
        jar_target = cache_dir / "jars" / group / artifact / version / f"{artifact}-{version}-javadoc.jar"
        download_file(
            maven_javadoc_url(repo_base, group, artifact, version),
            jar_target,
            force=force_download,
        )
        return jar_target

    if source_kind == "canton-scaladoc-tarball":
        if not isinstance(url_template, str) or "{version}" not in url_template:
            raise ValueError(
                f"Artifact {group}:{artifact} uses source_kind={source_kind!r} but does not provide a valid url_template"
            )
        archive_url = url_template.format(version=version)
        archive_target = cache_dir / "archives" / artifact / version / Path(archive_url).name
        jar_target = cache_dir / "jars" / group / artifact / version / f"{artifact}-{version}-scaladoc.jar"
        download_file(archive_url, archive_target, force=force_download)
        if force_download or not jar_target.exists():
            print(f"Packaging scaladoc archive as jar: {jar_target}")
            repackage_tarball_as_jar(archive_target, jar_target)
        else:
            print(f"Using cached jar: {jar_target}")
        return jar_target

    raise ValueError(f"Unsupported source_kind for {group}:{artifact}: {source_kind}")


def build_manifest(
    *,
    source_config: dict[str, Any],
    cache_dir: Path,
    manifest_path: Path,
    include_versions: set[str] | None,
    repo_base_override: str | None,
    force_download: bool,
) -> Path:
    repo_base = repo_base_override or str(source_config.get("repo_base") or "https://repo1.maven.org/maven2")
    artifacts_payload: list[dict[str, Any]] = []

    artifacts = source_config.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("Source config must contain an `artifacts` list")

    for artifact_entry in artifacts:
        if not isinstance(artifact_entry, dict):
            continue
        group = artifact_entry.get("group")
        artifact = artifact_entry.get("artifact")
        language = artifact_entry.get("language")
        versions = artifact_entry.get("versions")
        include_prefixes = artifact_entry.get("include_prefixes") or []
        source_kind = artifact_entry.get("source_kind") or "maven-javadoc-jar"
        url_template = artifact_entry.get("url_template")
        if not isinstance(group, str) or not group:
            continue
        if not isinstance(artifact, str) or not artifact:
            continue
        if language not in {"java", "scala"}:
            continue
        if not isinstance(versions, list):
            continue

        version_entries: list[dict[str, str]] = []
        for version in versions:
            if not isinstance(version, str) or not version:
                continue
            if include_versions is not None and version not in include_versions:
                continue

            jar_target = resolve_cached_jar(
                repo_base=repo_base,
                cache_dir=cache_dir,
                group=group,
                artifact=artifact,
                version=version,
                source_kind=str(source_kind),
                url_template=str(url_template) if isinstance(url_template, str) else None,
                force_download=force_download,
            )
            version_entries.append(
                {
                    "version": version,
                    "jar_path": str(jar_target.resolve()),
                }
            )

        if not version_entries:
            continue

        artifacts_payload.append(
            {
                "group": group,
                "artifact": artifact,
                "language": language,
                "include_prefixes": [prefix for prefix in include_prefixes if isinstance(prefix, str)],
                "versions": version_entries,
            }
        )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": source_config.get("source") or "digital-asset/docs local JVM docs cache",
        "repo_base": repo_base,
        "artifacts": artifacts_payload,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    return manifest_path


def build_command(args: argparse.Namespace, manifest_path: Path) -> list[str]:
    render_overview_file = DEFAULT_RENDER_ROOT / "ledger-api-jvm-bindings.mdx"
    render_details_dir = DEFAULT_RENDER_ROOT / "details"
    command = [
        "x2mdx",
        "jvm-docs",
        "build-api-pages-from-manifest",
        "--manifest",
        str(manifest_path.resolve()),
        "--overview-file",
        str(render_overview_file.resolve()),
        "--details-dir",
        str(render_details_dir.resolve()),
        "--overview-title",
        args.overview_title,
        "--source-name",
        args.source_name,
        "--version-filter",
        args.version_filter,
    ]
    for version in args.version or []:
        command.extend(["--version", version])
    return command


def render_output_paths() -> tuple[Path, Path]:
    return DEFAULT_RENDER_ROOT / "ledger-api-jvm-bindings.mdx", DEFAULT_RENDER_ROOT / "details"


def rewrite_markdown_links(text: str, replacements: list[tuple[str, str]]) -> str:
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def major_minor_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) < 2:
        raise ValueError(f"Expected semantic version with major.minor components, got: {version}")
    return ".".join(parts[:2])


def rewrite_upstream_docs_links(text: str, artifact_entry: dict[str, Any]) -> str:
    template = artifact_entry.get("upstream_docs_base_url_template")
    group = artifact_entry.get("group")
    artifact = artifact_entry.get("artifact")
    versions = artifact_entry.get("versions")
    if not isinstance(template, str) or not template:
        return text
    if not isinstance(group, str) or not isinstance(artifact, str):
        return text
    if not isinstance(versions, list):
        return text

    for version in versions:
        if not isinstance(version, str) or not version:
            continue
        old_prefix = f"https://javadoc.io/doc/{group}/{artifact}/{version}/"
        new_prefix = template.format(version=version, major_minor=major_minor_version(version)).rstrip("/") + "/"
        text = text.replace(old_prefix, new_prefix)
    return text


def copy_rewritten_page(
    source: Path,
    target: Path,
    replacements: list[tuple[str, str]],
    *,
    artifact_entry: dict[str, Any] | None = None,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8")
    text = rewrite_markdown_links(text, replacements)
    if artifact_entry is not None:
        text = rewrite_upstream_docs_links(text, artifact_entry)
    target.write_text(text, encoding="utf-8")


def publish_rendered_pages(
    *,
    source_config: dict[str, Any],
    publish_overview_file: Path,
    publish_root: Path,
) -> tuple[Path, set[str]]:
    render_overview_file, render_details_dir = render_output_paths()
    publish_root.mkdir(parents=True, exist_ok=True)

    artifact_entries = [
        entry
        for entry in source_config.get("artifacts", [])
        if isinstance(entry, dict)
        and isinstance(entry.get("artifact"), str)
        and isinstance(entry.get("language"), str)
        and entry.get("language") in LANGUAGE_DIRS
    ]

    preserved_language_dirs = {
        LANGUAGE_DIRS[str(entry["language"])]
        for entry in artifact_entries
        if bool(entry.get("preserve_existing_output"))
    }
    for language_dir in LANGUAGE_DIRS.values():
        if language_dir in preserved_language_dirs:
            continue
        shutil.rmtree(publish_root / language_dir, ignore_errors=True)
    if publish_overview_file.exists():
        publish_overview_file.unlink()
    if LEGACY_OVERVIEW_FILE.exists():
        LEGACY_OVERVIEW_FILE.unlink()
    shutil.rmtree(LEGACY_DETAILS_DIR, ignore_errors=True)

    overview_replacements: list[tuple[str, str]] = []
    generated_refs: set[str] = set()

    for artifact_entry in artifact_entries:
        artifact = str(artifact_entry["artifact"])
        language = str(artifact_entry["language"])
        preserve_existing_output = bool(artifact_entry.get("preserve_existing_output"))
        language_dir = publish_root / LANGUAGE_DIRS[language]
        artifact_slug = slugify(artifact)
        source_artifact_page = render_details_dir / f"{artifact_slug}.mdx"
        source_package_dir = render_details_dir / f"{artifact_slug}-packages"
        target_artifact_page = language_dir / "index.mdx"

        overview_replacements.append((f"({render_details_dir.name}/{artifact_slug})", f"({LANGUAGE_DIRS[language]})"))
        if preserve_existing_output:
            continue
        copy_rewritten_page(
            source_artifact_page,
            target_artifact_page,
            replacements=[(f"({source_package_dir.name}/", "(")],
            artifact_entry=artifact_entry,
        )
        generated_refs.add(docs_json_page_ref(target_artifact_page, DEFAULT_DOCS_JSON))

        if not source_package_dir.exists():
            continue
        language_dir.mkdir(parents=True, exist_ok=True)
        for package_page in sorted(source_package_dir.glob("*.mdx")):
            target_package_page = language_dir / package_page.name
            copy_rewritten_page(
                package_page,
                target_package_page,
                replacements=[(f"(../{artifact_slug})", "(index)")],
                artifact_entry=artifact_entry,
            )
            generated_refs.add(docs_json_page_ref(target_package_page, DEFAULT_DOCS_JSON))

    copy_rewritten_page(render_overview_file, publish_overview_file, replacements=overview_replacements)
    generated_refs.add(docs_json_page_ref(publish_overview_file, DEFAULT_DOCS_JSON))
    return publish_overview_file, generated_refs


def main() -> int:
    args = parse_args()
    source_config = load_json(Path(args.source_config).resolve())
    include_versions = set(args.version) if args.version else None
    manifest_path = build_manifest(
        source_config=source_config,
        cache_dir=Path(args.cache_dir).resolve(),
        manifest_path=Path(args.manifest_out).resolve(),
        include_versions=include_versions,
        repo_base_override=args.repo_base,
        force_download=args.force_download,
    )
    command = build_command(args, manifest_path)
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode != 0:
        return completed.returncode

    publish_overview_file, _ = publish_rendered_pages(
        source_config=source_config,
        publish_overview_file=Path(args.overview_file).resolve(),
        publish_root=Path(args.details_dir).resolve(),
    )
    update_docs_navigation(
        docs_json_path=Path(args.docs_json).resolve(),
        dropdown_label=args.nav_dropdown,
        parent_groups=args.nav_group or [],
        group_label=args.overview_title,
        overview_file=publish_overview_file.resolve(),
        publish_root=Path(args.details_dir).resolve(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
