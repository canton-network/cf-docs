#!/usr/bin/env python3
"""Add external snippet manifest entries from a local source checkout."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.generate_external_snippets import REPOS, SnippetRepo


CF_DOCS_ROOT = Path(__file__).resolve().parents[1]
MAIN_VERSION = "main"
NAME_LENGTH_LIMIT = 100

# Extension table for --language defaults. Anything else needs --language.
LANGUAGES = {
    ".conf": "hocon",
    ".daml": "daml",
    ".js": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".py": "python",
    ".rst": "rst",
    ".scala": "scala",
    ".sh": "bash",
    ".sql": "sql",
    ".toml": "toml",
    ".ts": "typescript",
    ".yaml": "yaml",
    ".yml": "yaml",
}


class SnippetAuthoringError(Exception):
    """A contributor-facing snippet authoring error."""


@dataclass(frozen=True)
class FileChange:
    heading: str
    path: Path
    content: bytes


def manifest_path(repo: SnippetRepo) -> Path:
    return CF_DOCS_ROOT / "config" / "snippet-config" / repo.config_name


def helper_path() -> Path:
    return CF_DOCS_ROOT / "scripts" / "helpers" / "generateOutputDocs.js"


def output_path(repo: SnippetRepo, snippet_name: str) -> Path:
    return (
        CF_DOCS_ROOT
        / "docs-main"
        / "snippets"
        / "external"
        / (repo.output_repo_name or repo.name)
        / MAIN_VERSION
        / f"{snippet_name}.mdx"
    )


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SnippetAuthoringError(f"Snippet manifest does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise SnippetAuthoringError(
            f"Snippet manifest is not valid JSON: {path}: {error}"
        ) from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("snippets"), list):
        raise SnippetAuthoringError(
            f'Snippet manifest must contain a top-level "snippets" array: {path}'
        )
    if not all(isinstance(item, dict) for item in manifest["snippets"]):
        raise SnippetAuthoringError(f"Every snippet entry must be an object: {path}")
    return manifest


def validate_source_dir(source_dir: Path) -> Path:
    if not source_dir.is_dir():
        raise SnippetAuthoringError(f"--source-dir is not a directory: {source_dir}")
    return source_dir


def normalized_source_path(source: str) -> str:
    if not source or source.startswith("/") or "\\" in source:
        raise SnippetAuthoringError(
            "--source must be a non-empty checkout-relative POSIX path"
        )
    parts = source.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SnippetAuthoringError(
            "--source must not contain empty, '.' or '..' path components"
        )
    return PurePosixPath(*parts).as_posix()


def validate_source_file(source_dir: Path, source: str) -> Path:
    root = source_dir.resolve()
    candidate = (root / source).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise SnippetAuthoringError(f"Snippet source escapes its checkout: {source}") from error
    if not candidate.is_file():
        raise SnippetAuthoringError(f"Snippet source file does not exist: {candidate}")
    return candidate


def infer_language(source: str) -> str:
    suffix = PurePosixPath(source).suffix.lower()
    language = LANGUAGES.get(suffix)
    if not language:
        known = ", ".join(sorted(LANGUAGES))
        raise SnippetAuthoringError(
            f"Cannot infer a language from {source!r}; pass --language explicitly "
            f"(known extensions: {known})"
        )
    return language


def selector(marker: str | None) -> dict[str, Any]:
    if marker is None:
        return {"type": "fullFile"}
    if not marker or "/" in marker or marker != marker.strip():
        raise SnippetAuthoringError(f"--marker must be a non-empty marker base name: {marker!r}")
    return {"type": "stringMarker", "start": f"{marker}_START", "end": f"{marker}_END"}


def _path_slug(value: str) -> str:
    return re.sub(r"[/.]", "-", value)


def derive_snippet_name(repo: SnippetRepo, source: str, location: dict[str, Any]) -> str:
    """Derive the stable snippet name.

    Base rule: strip the extension, replace ``/`` and ``.`` with ``-``, prefix
    ``<repo>-literal-full-`` or ``<repo>-literal-marker-``; for markers append the
    lowercased start marker with ``_`` as ``-``.

    Shortening: when the base result exceeds NAME_LENGTH_LIMIT and the path has three
    or more segments, keep the first segment and the file stem, and replace the
    segments between with the first six hex characters of SHA-256 over those
    segments joined by ``/``. The marker suffix is never shortened.
    """
    stem_path = re.sub(r"\.[^./]+$", "", source)
    kind = "full" if location["type"] == "fullFile" else "marker"
    suffix = ""
    if kind == "marker":
        suffix = "-" + str(location["start"]).lower().replace("_", "-")
    prefix = f"{repo.name}-literal-{kind}-"
    base = f"{prefix}{_path_slug(stem_path)}{suffix}"
    segments = stem_path.split("/")
    if len(base) <= NAME_LENGTH_LIMIT or len(segments) < 3:
        return base
    first, stem, middle = segments[0], segments[-1], segments[1:-1]
    digest = hashlib.sha256("/".join(middle).encode("utf-8")).hexdigest()[:6]
    return f"{prefix}{_path_slug(first)}-{digest}-{_path_slug(stem)}{suffix}"


def duplicate_name_locations(name: str) -> list[Path]:
    matches: list[Path] = []
    config_dir = CF_DOCS_ROOT / "config" / "snippet-config"
    for path in sorted(config_dir.glob("*-snippet-list-remote.json")):
        manifest = load_manifest(path)
        if any(entry.get("snippetName") == name for entry in manifest["snippets"]):
            matches.append(path)
    return matches


def same_source(entry: dict[str, Any], source: str, location: dict[str, Any]) -> bool:
    return entry.get("sourceFilepath") == source and entry.get("location") == location


def render_one_snippet(*, source_dir: Path, manifest: dict[str, Any], entry: dict[str, Any]) -> bytes:
    helper = helper_path()
    if not helper.is_file():
        raise SnippetAuthoringError(f"Snippet extraction helper does not exist: {helper}")

    single_manifest = {key: value for key, value in manifest.items() if key != "snippets"}
    single_manifest["snippets"] = [entry]
    with tempfile.TemporaryDirectory(prefix="cf-docs-snippet-") as temp_name:
        temp = Path(temp_name)
        config = temp / "exportConfig.json"
        output = temp / "output"
        config.write_text(
            json.dumps(single_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "node", str(helper),
                "--repo-root", str(source_dir),
                "--export-config", str(config),
                "--output", str(output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            raise SnippetAuthoringError(f"Snippet extraction failed:\n{details}")
        generated = output / f"{entry['snippetName']}.mdx"
        if not generated.is_file():
            raise SnippetAuthoringError(
                f"Snippet extraction did not create expected output: {generated}"
            )
        return generated.read_bytes()


_WS = re.compile(r"\s*")


def insert_manifest_entry(text: str, entry: dict[str, Any]) -> str:
    """Insert ``entry`` into the ``snippets`` array of ``text`` textually.

    The entry goes immediately before the first existing entry whose snippetName
    sorts after it, or at the end. Every other byte of the manifest is preserved.
    """
    header = re.search(r'"snippets"\s*:\s*\[', text)
    if not header:
        raise SnippetAuthoringError('Snippet manifest has no "snippets" array to insert into')
    decoder = json.JSONDecoder()
    position = header.end()
    elements: list[tuple[int, int, dict[str, Any]]] = []
    while True:
        position = _WS.match(text, position).end()
        if text.startswith("]", position):
            close = position
            break
        value, end = decoder.raw_decode(text, position)
        if not isinstance(value, dict):
            raise SnippetAuthoringError("Snippet manifest entries must be objects")
        elements.append((position, end, value))
        position = _WS.match(text, end).end()
        if text.startswith(",", position):
            position += 1

    if elements:
        line_start = text.rfind("\n", 0, elements[0][0]) + 1
        indent = text[line_start:elements[0][0]]
        if indent.strip():
            indent = "    "
    else:
        indent = "    "
    rendered = json.dumps(entry, indent=2, ensure_ascii=False).replace("\n", "\n" + indent)

    name = entry["snippetName"]
    for start, _end, existing in elements:
        if str(existing.get("snippetName", "")) > name:
            return text[:start] + rendered + ",\n" + indent + text[start:]
    if elements:
        last_end = elements[-1][1]
        return text[:last_end] + ",\n" + indent + rendered + text[last_end:]
    closing_indent = indent[:-2] if indent.endswith("  ") else ""
    return text[:header.end()] + "\n" + indent + rendered + "\n" + closing_indent + text[close:]


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def commit_changes(changes: list[FileChange]) -> None:
    originals = {
        change.path: change.path.read_bytes() if change.path.exists() else None
        for change in changes
    }
    try:
        for change in changes:
            atomic_write(change.path, change.content)
    except BaseException:
        for path, original in originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, original)
        raise


NO_NEWLINE = "\\ No newline at end of file\n"


def render_unified_diff(path: Path, proposed: bytes) -> str:
    original = path.read_bytes() if path.exists() else b""
    try:
        label = path.relative_to(CF_DOCS_ROOT).as_posix()
    except ValueError:
        label = str(path)
    diff = difflib.unified_diff(
        original.decode("utf-8").splitlines(keepends=True),
        proposed.decode("utf-8").splitlines(keepends=True),
        fromfile=f"a/{label}" if path.exists() else "/dev/null",
        tofile=f"b/{label}",
    )
    rendered: list[str] = []
    for line in diff:
        if line.endswith("\n"):
            rendered.append(line)
        else:
            # difflib drops the final newline; git marks that explicitly.
            rendered.append(line + "\n" + NO_NEWLINE)
    return "".join(rendered)


def print_change_preview(*, snippet_name: str, changes: list[FileChange]) -> None:
    print(f"Dry run: would add {snippet_name}; no files written")
    for change in changes:
        print(f"\n{change.heading}:")
        rendered = render_unified_diff(change.path, change.content)
        print(rendered if rendered else "(no changes)", end="" if rendered else "\n")


def component_name(repo: SnippetRepo, snippet_name: str) -> str:
    words = re.findall(
        r"[A-Za-z0-9]+",
        f"external-{repo.output_repo_name or repo.name}-{MAIN_VERSION}-{snippet_name}",
    )
    return "".join(word[:1].upper() + word[1:] for word in words)


def print_usage(repo: SnippetRepo, snippet_name: str) -> None:
    name = component_name(repo, snippet_name)
    path = (
        f"/snippets/external/{repo.output_repo_name or repo.name}/"
        f"{MAIN_VERSION}/{snippet_name}.mdx"
    )
    print("\nAdd this to the page:")
    print(f"import {name} from '{path}';")
    print(f"\n<{name} />")


def add(args: argparse.Namespace, repo: SnippetRepo) -> int:
    source_dir = validate_source_dir(args.source_dir)
    source = normalized_source_path(args.source)
    validate_source_file(source_dir, source)
    location = selector(args.marker)
    language = args.language or infer_language(source)
    name = derive_snippet_name(repo, source, location)

    manifest_file = manifest_path(repo)
    manifest_text = manifest_file.read_text(encoding="utf-8") if manifest_file.exists() else ""
    manifest = load_manifest(manifest_file)
    duplicates = duplicate_name_locations(name)
    if duplicates:
        locations = ", ".join(str(path) for path in duplicates)
        raise SnippetAuthoringError(f"Snippet name already exists: {name} ({locations})")
    for entry in manifest["snippets"]:
        if same_source(entry, source, location):
            raise SnippetAuthoringError(
                f"A snippet already uses this source and selector: {entry.get('snippetName')}"
            )
    generated_file = output_path(repo, name)
    if generated_file.exists():
        raise SnippetAuthoringError(
            f"Refusing to overwrite an existing output not owned by the manifest: {generated_file}"
        )

    entry = {
        "snippetName": name,
        "sourceRepo": repo.name,
        "sourceFilepath": source,
        "location": location,
        "description": "",
        "options": {"language": language},
    }
    generated = render_one_snippet(source_dir=source_dir, manifest=manifest, entry=entry)
    new_manifest_text = insert_manifest_entry(manifest_text, entry)
    changes = [
        FileChange("Manifest diff", manifest_file, new_manifest_text.encode("utf-8")),
        FileChange("Generated MDX diff", generated_file, generated),
    ]
    if args.dry_run:
        print_change_preview(snippet_name=name, changes=changes)
        print_usage(repo, name)
        return 0
    commit_changes(changes)

    print(f"Added {name}")
    print(f"Manifest: {manifest_file.relative_to(CF_DOCS_ROOT)}")
    print(f"Output:   {generated_file.relative_to(CF_DOCS_ROOT)}")
    print_usage(repo, name)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add cf-docs external snippets")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_parser = subparsers.add_parser("add", help="Add and render one snippet from a local checkout")
    add_parser.add_argument(
        "repo", metavar="repo", choices=sorted(REPOS),
        help=f"Source repository key: {', '.join(sorted(REPOS))}",
    )
    add_parser.add_argument(
        "--source-dir", type=Path, required=True,
        help="Local checkout of the source repository (required; never inferred)",
    )
    add_parser.add_argument(
        "--source", required=True,
        help="Source file path relative to --source-dir",
    )
    add_parser.add_argument(
        "--marker",
        help="Marker base name; extracts between <NAME>_START and <NAME>_END. Omit for the whole file",
    )
    add_parser.add_argument(
        "--language",
        help="Code fence language; defaults from the file extension",
    )
    add_parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate, print manifest and MDX diffs, write nothing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo = REPOS[args.repo]
    try:
        return add(args, repo)
    except (OSError, SnippetAuthoringError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
