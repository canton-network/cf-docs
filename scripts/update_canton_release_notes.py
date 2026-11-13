#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import canton_release_reference
from generated_reference_sources import canton_release_bundles

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "ledger-api" / "source-artifacts.json"
DEFAULT_RELEASE_REPO = canton_release_reference.DEFAULT_RELEASE_REPO
# Every published release from this version onward is on the page, across all release lines.
DEFAULT_MIN_VERSION = "3.5.0"
DOCS_MAIN = REPO_ROOT / "docs-main"
DEFAULT_RELEASE_INDEX = DOCS_MAIN / "global-synchronizer" / "release-notes" / "canton.mdx"
# Per-release pages from before the releases were combined on one page; removed and redirected.
DEFAULT_RELEASE_DIR = DOCS_MAIN / "global-synchronizer" / "release-notes" / "canton-releases"
DEFAULT_LEGACY_RELEASE_PAGE = DOCS_MAIN / "global-synchronizer" / "release-notes" / "canton" / "index.mdx"
DEFAULT_LEGACY_RELEASE_DIR = DOCS_MAIN / "global-synchronizer" / "release-notes" / "canton"
DEFAULT_DOCS_JSON = DOCS_MAIN / "docs.json"
USER_AGENT = "cf-docs-canton-release-note-updater"
DOWNLOAD_TIMEOUT_SECONDS = 300.0
RELEASE_HEADING_RE = re.compile(r"^# Release of Canton (?P<version>\d+\.\d+\.\d+)\s*$", re.MULTILINE)
CANTON_RELEASE_LINK_RE = re.compile(
    r"/global-synchronizer/release-notes/(?:canton|canton-releases)/(?P<slug>\d+-\d+-\d+)"
)
# A release section on the combined page, optionally with its custom heading ID.
RELEASE_SECTION_RE = re.compile(
    r"^## Release of Canton (?P<version>\d+\.\d+\.\d+)(?: \{#[^}]+\})?[ \t]*$", re.MULTILINE
)
PAGE_RELEASE_VERSION_RE = re.compile(r"^#{1,2} Release of Canton (?P<version>\d+\.\d+\.\d+)\b", re.MULTILINE)
HEADING_RE = re.compile(r"^(?P<hashes>#{1,6}) (?P<text>.*?)(?: \{#(?P<id>[^}]+)\})?\s*$")
# Mintlify drops level-5 and level-6 headings that carry {#id}, so those get an anchor element instead.
HEADING_ANCHOR_RE = re.compile(r'^<a id="(?P<id>[^"]+)" />$')
MAX_CUSTOM_ID_LEVEL = 4
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
IN_PAGE_LINK_RE = re.compile(r"\]\(#(?P<anchor>[^)\s]+)\)")
CROSS_RELEASE_LINK_RE = re.compile(
    r"\]\((?P<prefix>(?:https://docs\.canton\.network)?)/global-synchronizer/release-notes/"
    r"(?:canton-releases|canton)/(?P<slug>\d+-\d+-\d+)(?:#(?P<anchor>[^)\s]+))?\)"
)
RELEASE_SLUG_RE = re.compile(r"\d+-\d+-\d+")
ANGLE_PLACEHOLDER_RE = re.compile(r"<([^>\n]+)>")
CANTON_PAGE_REF = "global-synchronizer/release-notes/canton"
CANTON_PAGE_URL = f"/{CANTON_PAGE_REF}"
CANTON_RELEASE_PAGE_ROOT = "global-synchronizer/release-notes/canton-releases"
CANTON_PAGE_TITLE = "Canton"
CANTON_PAGE_DESCRIPTION = "Release notes for Canton."


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> Version:
        parts = value.split(".")
        if len(parts) != 3:
            raise ValueError(f"Expected MAJOR.MINOR.PATCH version, got {value!r}")
        return cls(*(int(part) for part in parts))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ReleaseNoteSource:
    version: Version
    url: str
    archive_path: str


@dataclass(frozen=True)
class PageUpdate:
    previous_versions: tuple[str, ...]
    current_versions: tuple[str, ...]
    source_paths: tuple[str, ...]
    changed: bool


def published_release_versions(*, release_repo: str) -> tuple[Version, ...]:
    """Return stable versions with a published, non-prerelease GitHub release.

    A tag or a public bundle alone does not count as a release.
    """
    versions: set[Version] = set()
    page = 1
    while True:
        releases = canton_release_reference.github_api_json(
            f"repos/{release_repo}/releases?per_page=100&page={page}"
        )
        if not isinstance(releases, list):
            raise ValueError(f"Expected a list of GitHub releases for {release_repo}")
        if not releases:
            break
        for release in releases:
            if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
                continue
            tag = release.get("tag_name")
            match = canton_release_reference.STABLE_TAG_RE.fullmatch(tag) if isinstance(tag, str) else None
            if match is not None:
                versions.add(Version.parse(match.group("version")))
        page += 1
    return tuple(sorted(versions))


def release_note_sources(
    *,
    source_config_path: Path,
    release_repo: str,
    min_version: Version,
    version_prefix: str | None,
) -> tuple[ReleaseNoteSource, ...]:
    source_config = canton_release_bundles.parse_source_config(source_config_path)
    versions = tuple(
        str(version)
        for version in published_release_versions(release_repo=release_repo)
        if version >= min_version
        and (version_prefix is None or str(version).startswith(f"{version_prefix}."))
        and canton_release_bundles.release_bundle_exists(source_config, canton_version=str(version))
    )
    if not versions:
        raise RuntimeError(f"No published Canton releases with public bundles found from {min_version}")
    return tuple(
        ReleaseNoteSource(
            version=Version.parse(version),
            url=canton_release_bundles.release_url(source_config, canton_version=version),
            archive_path=f"canton-open-source-{version}/RELEASE-NOTES.md",
        )
        for version in versions
    )


def fetch_release_note_markdown(
    *,
    source: ReleaseNoteSource,
) -> str:
    request = urllib.request.Request(
        source.url,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            with tarfile.open(fileobj=response, mode="r|gz") as archive:
                for member in archive:
                    if member.name != source.archive_path:
                        continue
                    release_notes = archive.extractfile(member)
                    if release_notes is None:
                        break
                    return release_notes.read().decode("utf-8")
    except (urllib.error.URLError, tarfile.TarError, UnicodeDecodeError) as error:
        raise RuntimeError(f"Could not read {source.archive_path} from {source.url}: {error}") from error
    raise RuntimeError(f"Could not find {source.archive_path} in {source.url}")


def current_release_version(page_text: str) -> str:
    match = RELEASE_HEADING_RE.search(page_text)
    if match is None:
        raise ValueError("Could not find '# Release of Canton X.Y.Z' heading in release-note page")
    return match.group("version")


def release_versions(text: str) -> tuple[str, ...]:
    versions = [match.group("version") for match in PAGE_RELEASE_VERSION_RE.finditer(text)]
    versions.extend(match.group("slug").replace("-", ".") for match in CANTON_RELEASE_LINK_RE.finditer(text))
    return tuple(dict.fromkeys(versions))


def normalized_release_markdown(markdown: str) -> str:
    body = markdown.strip()
    current_release_version(body)
    return escape_mdx_angle_placeholders(body)


def escape_mdx_angle_placeholders(markdown: str) -> str:
    escaped_lines: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            escaped_lines.append(line)
            continue
        if in_fence:
            escaped_lines.append(line)
            continue
        parts = line.split("`")
        for index in range(0, len(parts), 2):
            parts[index] = ANGLE_PLACEHOLDER_RE.sub(r"&lt;\1&gt;", parts[index])
            parts[index] = parts[index].replace("-->", "--&gt;")
        escaped_lines.append("`".join(parts))
    return "\n".join(escaped_lines)


def rewrite_release_page(page_text: str, release_markdown: str) -> str:
    frontmatter_end = page_text.find("---", 3)
    if not page_text.startswith("---\n") or frontmatter_end == -1:
        raise ValueError("Expected release-note index page to start with YAML frontmatter")
    return f"{page_text[: frontmatter_end + 3].rstrip()}\n\n{normalized_release_markdown(release_markdown)}\n"


def release_slug(version: Version) -> str:
    return str(version).replace(".", "-")


def release_heading_id(version: Version | str) -> str:
    return f"release-of-canton-{str(version).replace('.', '-')}"


def legacy_release_page_path(release_dir: Path, source: ReleaseNoteSource) -> Path:
    return release_dir / f"{release_slug(source.version)}.mdx"


def strip_frontmatter(page_text: str) -> str:
    if not page_text.startswith("---\n"):
        return page_text
    frontmatter_end = page_text.find("\n---", 3)
    if frontmatter_end == -1:
        raise ValueError("Unterminated YAML frontmatter")
    return page_text[frontmatter_end + 4 :]


def outside_fences(lines: Sequence[str]) -> Iterable[tuple[int, str]]:
    in_fence = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield index, line


def anchor_slug(text: str) -> str:
    text = MARKDOWN_LINK_RE.sub(r"\1", text)
    text = text.replace("`", "").replace("*", "").lower()
    text = re.sub(r"['’]", "", text)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def loose_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def demote_headings(markdown: str) -> str:
    lines = markdown.splitlines()
    for index, line in outside_fences(lines):
        match = HEADING_RE.match(line)
        if match is None:
            continue
        if len(match.group("hashes")) == 6:
            raise ValueError(f"Cannot demote level-6 heading: {line!r}")
        lines[index] = f"#{line}"
    return "\n".join(lines)


def assign_heading_ids(section: str, version: Version) -> str:
    """Give every heading an ID qualified by the release version.

    All releases share one page, so headings such as "Summary" or "Breaking changes"
    repeat. Fixed IDs keep each anchor unique and stable as new releases are added.
    """
    lines = section.splitlines()
    used: dict[str, int] = {}
    anchored: dict[int, str] = {}
    for index, line in outside_fences(lines):
        match = HEADING_RE.match(line)
        if match is None or heading_id_at(lines, index, match) is not None:
            continue
        text = match.group("text")
        if RELEASE_SECTION_RE.match(line):
            heading_id = release_heading_id(version)
        else:
            base = anchor_slug(text) or "section"
            used[base] = used.get(base, 0) + 1
            suffix = "" if used[base] == 1 else f"-{used[base]}"
            heading_id = f"{base}{suffix}-{release_slug(version)}"
        if len(match.group("hashes")) <= MAX_CUSTOM_ID_LEVEL:
            lines[index] = f"{match.group('hashes')} {text} {{#{heading_id}}}"
        else:
            anchored[index] = heading_id
    for index in sorted(anchored, reverse=True):
        lines.insert(index, f'<a id="{anchored[index]}" />')
    return "\n".join(lines)


def heading_id_at(lines: Sequence[str], index: int, match: re.Match[str]) -> str | None:
    if match.group("id"):
        return match.group("id")
    anchor = HEADING_ANCHOR_RE.match(lines[index - 1]) if index > 0 else None
    return anchor.group("id") if anchor is not None else None


def release_section(markdown: str, version: Version) -> str:
    """Convert one RELEASE-NOTES.md (or legacy per-release page body) into a page section."""
    body = normalized_release_markdown(markdown)
    if current_release_version(body) != str(version):
        raise ValueError(f"Release notes for {version} start with a heading for another release")
    return assign_heading_ids(demote_headings(body), version)


def section_headings(section: str) -> list[tuple[str, str]]:
    lines = section.splitlines()
    headings: list[tuple[str, str]] = []
    for index, line in outside_fences(lines):
        match = HEADING_RE.match(line)
        heading_id = heading_id_at(lines, index, match) if match is not None else None
        if match is not None and heading_id is not None:
            headings.append((match.group("text"), heading_id))
    return headings


def resolve_anchor(target: str, headings: Sequence[tuple[str, str]], page_ids: set[str]) -> str:
    """Map an anchor written for a standalone release page to the heading's ID on the combined page."""
    if target in page_ids:
        return target
    matches = [heading_id for text, heading_id in headings if loose_key(anchor_slug(text)) == loose_key(target)]
    if matches:
        return matches[0]
    numbered = re.fullmatch(r"(?P<base>.+)-(?P<count>\d+)", target)
    if numbered is not None:
        count = int(numbered.group("count"))
        base = loose_key(numbered.group("base"))
        matches = [heading_id for text, heading_id in headings if loose_key(anchor_slug(text)) == base]
        if len(matches) >= count:
            return matches[count - 1]
    raise ValueError(f"Could not resolve anchor #{target}")


def resolve_release_links(sections: dict[Version, str]) -> dict[Version, str]:
    headings = {version: section_headings(section) for version, section in sections.items()}
    page_ids = {heading_id for version_headings in headings.values() for _text, heading_id in version_headings}

    def cross_release(match: re.Match[str]) -> str:
        version = Version.parse(match.group("slug").replace("-", "."))
        if version not in headings:
            raise ValueError(f"Link to Canton {version}, which is not on the release-notes page")
        target = match.group("anchor")
        heading_id = (
            release_heading_id(version) if target is None else resolve_anchor(target, headings[version], page_ids)
        )
        return f"]({match.group('prefix')}{CANTON_PAGE_URL}#{heading_id})"

    resolved: dict[Version, str] = {}
    for version, section in sections.items():
        text = CROSS_RELEASE_LINK_RE.sub(cross_release, section)

        def same_release(match: re.Match[str], version: Version = version) -> str:
            try:
                return f"](#{resolve_anchor(match.group('anchor'), headings[version], page_ids)})"
            except ValueError as error:
                raise ValueError(f"Canton {version}: {error}") from error

        resolved[version] = IN_PAGE_LINK_RE.sub(same_release, text)
    return resolved


def existing_sections(page_text: str) -> dict[Version, str]:
    body = strip_frontmatter(page_text)
    matches = list(RELEASE_SECTION_RE.finditer(body))
    sections: dict[Version, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[Version.parse(match.group("version"))] = body[match.start() : end].strip()
    return sections


def release_page_markdown(sections: dict[Version, str]) -> str:
    lines = [
        "---",
        f'title: "{CANTON_PAGE_TITLE}"',
        f'description: "{CANTON_PAGE_DESCRIPTION}"',
        "---",
        "",
        "{/* Generated from the RELEASE-NOTES.md files in public Canton release bundles. */}",
        "",
        "Canton release notes are reproduced below from the published Canton release bundles.",
    ]
    for version in sorted(sections, reverse=True):
        lines.extend(["", sections[version]])
    return "\n".join(lines) + "\n"


def read_source_markdown(
    *,
    sources: Sequence[ReleaseNoteSource],
) -> dict[ReleaseNoteSource, str]:
    return {source: fetch_release_note_markdown(source=source) for source in sources}


def build_release_page(
    *,
    previous_text: str,
    release_dir: Path,
    sources: Sequence[ReleaseNoteSource],
    source_markdown: dict[ReleaseNoteSource, str],
) -> tuple[str, bool]:
    """Return the combined page and whether any selected release is still missing content."""
    current = existing_sections(previous_text)
    sections: dict[Version, str] = {}
    missing = False
    for source in sources:
        legacy_page = legacy_release_page_path(release_dir, source)
        if source.version in current:
            sections[source.version] = current[source.version]
        elif legacy_page.exists():
            legacy_markdown = strip_frontmatter(legacy_page.read_text(encoding="utf-8"))
            sections[source.version] = release_section(legacy_markdown, source.version)
        elif source in source_markdown:
            sections[source.version] = release_section(source_markdown[source], source.version)
        else:
            missing = True
    return release_page_markdown(resolve_release_links(sections)), missing


def write_release_page(
    *,
    release_index: Path,
    release_dir: Path,
    legacy_release_page: Path,
    legacy_release_dir: Path,
    page_text: str,
    missing_content: bool,
    dry_run: bool,
) -> tuple[bool, tuple[str, ...]]:
    """Write the combined page and delete per-release pages. Return (changed, removed release slugs)."""
    stale_files = set(release_dir.glob("*.mdx")) if release_dir.exists() else set()
    if legacy_release_page != release_index and legacy_release_page.exists():
        stale_files.add(legacy_release_page)
    if legacy_release_dir != release_dir and legacy_release_dir.exists():
        stale_files.update(legacy_release_dir.glob("*.mdx"))
    removed_slugs = tuple(
        sorted(path.stem for path in stale_files if path.parent == release_dir and RELEASE_SLUG_RE.fullmatch(path.stem))
    )
    current_text = release_index.read_text(encoding="utf-8") if release_index.exists() else None
    changed = missing_content or current_text != page_text or bool(stale_files)

    if dry_run or not changed:
        return changed, removed_slugs

    release_index.parent.mkdir(parents=True, exist_ok=True)
    release_index.write_text(page_text, encoding="utf-8")
    for path in stale_files:
        path.unlink()
    if release_dir.exists() and not any(release_dir.iterdir()):
        release_dir.rmdir()
    return True, removed_slugs


def replace_canton_nav_entry(pages: list[object]) -> None:
    insert_at: int | None = None
    filtered: list[object] = []
    for item in pages:
        if isinstance(item, str) and (
            item == CANTON_PAGE_REF
            or item.startswith(f"{CANTON_PAGE_REF}/")
            or item.startswith(f"{CANTON_RELEASE_PAGE_ROOT}/")
        ):
            insert_at = len(filtered)
            continue
        if isinstance(item, dict) and item.get("group") == "Canton":
            insert_at = len(filtered)
            continue
        filtered.append(item)
        if item == "global-synchronizer/release-notes/splice":
            insert_at = len(filtered)
    if insert_at is None:
        insert_at = len(filtered)
    filtered.insert(insert_at, CANTON_PAGE_REF)
    pages[:] = filtered


def add_release_redirects(docs: dict[str, object], removed_slugs: Sequence[str]) -> None:
    redirects = docs.setdefault("redirects", [])
    if not isinstance(redirects, list):
        raise ValueError("docs.json redirects must be a list")
    sources = {redirect.get("source") for redirect in redirects if isinstance(redirect, dict)}
    for slug in sorted(removed_slugs, key=lambda value: Version.parse(value.replace("-", ".")), reverse=True):
        source = f"/{CANTON_RELEASE_PAGE_ROOT}/{slug}"
        if source in sources:
            continue
        redirects.append({"source": source, "destination": f"{CANTON_PAGE_URL}#{release_heading_id(slug)}"})


def update_docs_json(*, docs_json: Path, removed_slugs: Sequence[str], dry_run: bool) -> bool:
    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    products = docs.get("navigation", {}).get("products")
    if not isinstance(products, list):
        raise ValueError(f"{docs_json} must define navigation.products")

    for product in products:
        if not isinstance(product, dict):
            continue
        if product.get("product") == "Global Synchronizer":
            groups = product.get("groups")
            if isinstance(groups, list):
                for group in groups:
                    if isinstance(group, dict) and group.get("group") == "Release Notes":
                        pages = group.get("pages")
                        if isinstance(pages, list):
                            replace_canton_nav_entry(pages)
        if product.get("product") == "Release Notes":
            pages = product.get("pages")
            if isinstance(pages, list):
                for group in pages:
                    if isinstance(group, dict) and group.get("group") == "Canton Network":
                        group_pages = group.get("pages")
                        if isinstance(group_pages, list):
                            replace_canton_nav_entry(group_pages)
    add_release_redirects(docs, removed_slugs)

    updated = json.dumps(docs, indent=2) + "\n"
    before = docs_json.read_text(encoding="utf-8")
    if before == updated:
        return False
    if not dry_run:
        docs_json.write_text(updated, encoding="utf-8")
    return True


def update_release_page(
    *,
    release_index: Path,
    release_dir: Path,
    legacy_release_page: Path,
    legacy_release_dir: Path,
    docs_json: Path,
    source_config_path: Path,
    release_repo: str,
    min_version: Version,
    version_prefix: str | None,
    dry_run: bool,
) -> PageUpdate:
    previous_page = release_index if release_index.exists() else legacy_release_page
    previous_text = previous_page.read_text(encoding="utf-8") if previous_page.exists() else ""
    previous_versions = release_versions(previous_text)
    sources = release_note_sources(
        source_config_path=source_config_path,
        release_repo=release_repo,
        min_version=min_version,
        version_prefix=version_prefix,
    )
    on_page = existing_sections(previous_text)
    missing_sources = tuple(
        source
        for source in sources
        if source.version not in on_page and not legacy_release_page_path(release_dir, source).exists()
    )
    source_markdown = {} if dry_run else read_source_markdown(sources=missing_sources)
    page_text, missing_content = build_release_page(
        previous_text=previous_text,
        release_dir=release_dir,
        sources=sources,
        source_markdown=source_markdown,
    )
    changed_page, removed_slugs = write_release_page(
        release_index=release_index,
        release_dir=release_dir,
        legacy_release_page=legacy_release_page,
        legacy_release_dir=legacy_release_dir,
        page_text=page_text,
        missing_content=missing_content,
        dry_run=dry_run,
    )
    changed_nav = update_docs_json(docs_json=docs_json, removed_slugs=removed_slugs, dry_run=dry_run)
    return PageUpdate(
        previous_versions=previous_versions,
        current_versions=tuple(str(source.version) for source in sources),
        source_paths=tuple(f"{source.url}#{source.archive_path}" for source in sources),
        changed=changed_page or changed_nav,
    )


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update the published Canton release-notes page from release bundles.")
    parser.add_argument("--source-config", type=Path, default=DEFAULT_SOURCE_CONFIG)
    parser.add_argument("--release-repo", default=DEFAULT_RELEASE_REPO)
    parser.add_argument(
        "--min-version",
        type=Version.parse,
        default=Version.parse(DEFAULT_MIN_VERSION),
        help="Oldest published Canton release to include.",
    )
    parser.add_argument(
        "--version-prefix",
        help="Restrict source selection to a release line such as 3.5. Defaults to all release lines.",
    )
    parser.add_argument("--release-index", type=Path, default=DEFAULT_RELEASE_INDEX)
    parser.add_argument("--release-dir", type=Path, default=DEFAULT_RELEASE_DIR)
    parser.add_argument("--legacy-release-page", type=Path, default=DEFAULT_LEGACY_RELEASE_PAGE)
    parser.add_argument("--legacy-release-dir", type=Path, default=DEFAULT_LEGACY_RELEASE_DIR)
    parser.add_argument("--docs-json", type=Path, default=DEFAULT_DOCS_JSON)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(tuple(argv))


def main(argv: Iterable[str] = sys.argv[1:]) -> int:
    args = parse_args(argv)
    update = update_release_page(
        release_index=args.release_index,
        release_dir=args.release_dir,
        legacy_release_page=args.legacy_release_page,
        legacy_release_dir=args.legacy_release_dir,
        docs_json=args.docs_json,
        source_config_path=args.source_config,
        release_repo=args.release_repo,
        min_version=args.min_version,
        version_prefix=args.version_prefix,
        dry_run=args.dry_run,
    )
    action = "Would update" if args.dry_run and update.changed else "Updated" if update.changed else "Already current"
    previous = ", ".join(update.previous_versions) or "none"
    current = ", ".join(update.current_versions)
    print(
        f"{action} Canton release notes: "
        f"{previous} -> {current} "
        "from public Canton release bundles"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
