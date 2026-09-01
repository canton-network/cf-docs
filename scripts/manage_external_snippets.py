#!/usr/bin/env python3
"""Add and edit external snippet manifest entries from a local source checkout."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.generate_external_snippets import REPOS, SnippetRepo, find_source_dir


CF_DOCS_ROOT = Path(__file__).resolve().parents[1]

LANGUAGES = {
    ".daml": "haskell",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "jsx",
    ".json": "json",
    ".md": "markdown",
    ".mdx": "mdx",
    ".proto": "protobuf",
    ".py": "python",
    ".scala": "scala",
    ".sh": "bash",
    ".sql": "sql",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".yaml": "yaml",
    ".yml": "yaml",
}


class SnippetAuthoringError(Exception):
    """A contributor-facing snippet authoring error."""


def manifest_path(repo: SnippetRepo) -> Path:
    return CF_DOCS_ROOT / "config" / "snippet-config" / repo.config_name


def helper_path() -> Path:
    return CF_DOCS_ROOT / "scripts" / "helpers" / "generateOutputDocs.js"


def output_path(repo: SnippetRepo, version: str, snippet_name: str) -> Path:
    return (
        CF_DOCS_ROOT
        / "docs-main"
        / "snippets"
        / "external"
        / (repo.output_repo_name or repo.name)
        / version
        / f"{snippet_name}.mdx"
    )


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SnippetAuthoringError(
            f"Snippet manifest does not exist: {path}"
        ) from error
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


def normalized_source_path(source: str) -> str:
    if not source or source.startswith("/") or "\\" in source:
        raise SnippetAuthoringError(
            "--source must be a non-empty repository-relative POSIX path"
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
        raise SnippetAuthoringError(
            f"Snippet source escapes its checkout: {source}"
        ) from error
    if not candidate.is_file():
        raise SnippetAuthoringError(f"Snippet source file does not exist: {candidate}")
    return candidate


def infer_language(source: str) -> str:
    suffix = PurePosixPath(source).suffix.lower()
    language = LANGUAGES.get(suffix)
    if not language:
        raise SnippetAuthoringError(
            f"Cannot infer a language from {source!r}; pass --language explicitly"
        )
    return language


def slug(value: str) -> str:
    rendered = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not rendered:
        raise SnippetAuthoringError(f"Cannot derive a name from {value!r}")
    return rendered


def path_slug(source: str) -> str:
    path = PurePosixPath(source)
    without_suffix = path.with_suffix("") if path.suffix else path
    return slug(without_suffix.as_posix())


def marker_pair(args: argparse.Namespace, *, editing: bool) -> dict[str, Any] | None:
    supplied_exact = bool(args.start_marker or args.end_marker)
    choices = int(args.full_file) + int(bool(args.marker)) + int(supplied_exact)
    if choices > 1:
        raise SnippetAuthoringError(
            "Choose only one selector: --full-file, --marker, or --start-marker/--end-marker"
        )
    if supplied_exact and not (args.start_marker and args.end_marker):
        raise SnippetAuthoringError(
            "Pass both --start-marker and --end-marker when using exact markers"
        )
    if args.full_file:
        return {"type": "fullFile"}
    if args.marker:
        return {
            "type": "stringMarker",
            "start": f"{args.marker}_START",
            "end": f"{args.marker}_END",
        }
    if supplied_exact:
        return {
            "type": "stringMarker",
            "start": args.start_marker,
            "end": args.end_marker,
        }
    if editing:
        return None
    return {"type": "fullFile"}


def validate_snippet_name(name: str) -> str:
    if not name or name.startswith("/") or "\\" in name:
        raise SnippetAuthoringError(
            "Snippet names must be non-empty relative POSIX paths"
        )
    if any(part in {"", ".", ".."} for part in name.split("/")):
        raise SnippetAuthoringError(
            "Snippet names must not contain empty, '.' or '..' path components"
        )
    return name


def validate_version(version: str) -> str:
    if not version or version in {".", ".."} or "/" in version or "\\" in version:
        raise SnippetAuthoringError("--version must be one non-empty path segment")
    return version


def derive_snippet_name(
    repo: SnippetRepo, source: str, location: dict[str, Any]
) -> str:
    name = f"{repo.name}-literal-"
    if location["type"] == "fullFile":
        return f"{name}full-{path_slug(source)}"
    return f"{name}marker-{path_slug(source)}-{slug(str(location['start']))}"


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


def render_one_snippet(
    *,
    source_dir: Path,
    manifest: dict[str, Any],
    entry: dict[str, Any],
) -> bytes:
    helper = helper_path()
    if not helper.is_file():
        raise SnippetAuthoringError(
            f"Snippet extraction helper does not exist: {helper}"
        )

    single_manifest = {
        key: value for key, value in manifest.items() if key != "snippets"
    }
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
                "node",
                str(helper),
                "--repo-root",
                str(source_dir),
                "--export-config",
                str(config),
                "--output",
                str(output),
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


def commit_manifest_and_output(
    manifest_file: Path,
    manifest: dict[str, Any],
    generated_file: Path,
    generated_content: bytes,
) -> None:
    original_manifest = manifest_file.read_bytes()
    original_output = generated_file.read_bytes() if generated_file.exists() else None
    manifest_content = (
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    try:
        atomic_write(manifest_file, manifest_content)
        atomic_write(generated_file, generated_content)
    except BaseException:
        atomic_write(manifest_file, original_manifest)
        if original_output is None:
            generated_file.unlink(missing_ok=True)
        else:
            atomic_write(generated_file, original_output)
        raise


def component_name(repo: SnippetRepo, version: str, snippet_name: str) -> str:
    words = re.findall(
        r"[A-Za-z0-9]+",
        f"external-{repo.output_repo_name or repo.name}-{version}-{snippet_name}",
    )
    return "".join(word[:1].upper() + word[1:] for word in words)


def print_usage(repo: SnippetRepo, version: str, snippet_name: str) -> None:
    name = component_name(repo, version, snippet_name)
    path = (
        f"/snippets/external/{repo.output_repo_name or repo.name}/"
        f"{version}/{snippet_name}.mdx"
    )
    print("\nAdd this to the page:")
    print(f"import {name} from '{path}';")
    print(f"\n<{name} />")


def source_dir_for(args: argparse.Namespace, repo: SnippetRepo) -> Path:
    try:
        return find_source_dir(repo, args.source_dir)
    except SystemExit as error:
        raise SnippetAuthoringError(str(error)) from error


def add(args: argparse.Namespace, repo: SnippetRepo) -> int:
    source_dir = source_dir_for(args, repo)
    version = validate_version(args.version)
    source = normalized_source_path(args.source)
    validate_source_file(source_dir, source)
    location = marker_pair(args, editing=False)
    assert location is not None
    language = args.language or infer_language(source)
    name = validate_snippet_name(
        args.name or derive_snippet_name(repo, source, location)
    )

    manifest_file = manifest_path(repo)
    manifest = load_manifest(manifest_file)
    duplicates = duplicate_name_locations(name)
    if duplicates:
        locations = ", ".join(str(path) for path in duplicates)
        raise SnippetAuthoringError(
            f"Snippet name already exists: {name} ({locations})"
        )
    for entry in manifest["snippets"]:
        if same_source(entry, source, location):
            raise SnippetAuthoringError(
                f"A snippet already uses this source and selector: {entry.get('snippetName')}"
            )

    entry = {
        "snippetName": name,
        "sourceRepo": repo.name,
        "sourceFilepath": source,
        "location": location,
        "description": "",
        "options": {"language": language},
    }
    generated = render_one_snippet(
        source_dir=source_dir,
        manifest=manifest,
        entry=entry,
    )
    manifest["snippets"].append(entry)
    generated_file = output_path(repo, version, name)
    if generated_file.exists():
        raise SnippetAuthoringError(
            f"Refusing to overwrite an existing output not owned by the manifest: "
            f"{generated_file}"
        )
    commit_manifest_and_output(manifest_file, manifest, generated_file, generated)

    print(f"Added {name}")
    print(f"Manifest: {manifest_file.relative_to(CF_DOCS_ROOT)}")
    print(f"Output:   {generated_file.relative_to(CF_DOCS_ROOT)}")
    print_usage(repo, version, name)
    return 0


def edit(args: argparse.Namespace, repo: SnippetRepo) -> int:
    source_dir = source_dir_for(args, repo)
    version = validate_version(args.version)
    manifest_file = manifest_path(repo)
    manifest = load_manifest(manifest_file)
    matches = [
        entry
        for entry in manifest["snippets"]
        if entry.get("snippetName") == args.snippet_name
    ]
    if len(matches) != 1:
        raise SnippetAuthoringError(
            f"Expected exactly one snippet named {args.snippet_name!r} in {manifest_file}; "
            f"found {len(matches)}"
        )
    entry = matches[0]
    requested_location = marker_pair(args, editing=True)
    has_change = any(
        (
            args.source is not None,
            requested_location is not None,
            args.language is not None,
        )
    )
    if not has_change:
        raise SnippetAuthoringError(
            "Edit requires --source, a selector option, or --language"
        )

    source = normalized_source_path(args.source or str(entry.get("sourceFilepath", "")))
    validate_source_file(source_dir, source)
    location = requested_location or entry.get("location")
    if not isinstance(location, dict) or location.get("type") not in {
        "fullFile",
        "stringMarker",
        "lines",
        "jsonIndex",
        "regexWrap",
    }:
        raise SnippetAuthoringError(
            f"Snippet has an unsupported existing selector: {location!r}"
        )
    options = entry.get("options")
    if not isinstance(options, dict):
        options = {}
        entry["options"] = options
    language = args.language or options.get("language") or infer_language(source)

    for other in manifest["snippets"]:
        if other is not entry and same_source(other, source, location):
            raise SnippetAuthoringError(
                f"Another snippet already uses this source and selector: "
                f"{other.get('snippetName')}"
            )

    entry["sourceRepo"] = repo.name
    entry["sourceFilepath"] = source
    entry["location"] = location
    options["language"] = language
    generated = render_one_snippet(
        source_dir=source_dir,
        manifest=manifest,
        entry=entry,
    )
    generated_file = output_path(repo, version, args.snippet_name)
    commit_manifest_and_output(manifest_file, manifest, generated_file, generated)

    print(f"Edited {args.snippet_name}; its import path is unchanged")
    print(f"Manifest: {manifest_file.relative_to(CF_DOCS_ROOT)}")
    print(f"Output:   {generated_file.relative_to(CF_DOCS_ROOT)}")
    return 0


def add_common_arguments(parser: argparse.ArgumentParser, *, editing: bool) -> None:
    parser.add_argument("repo", choices=sorted(REPOS), help="Source repository key")
    if editing:
        parser.add_argument("snippet_name", help="Existing stable snippetName")
        parser.add_argument("--source")
    else:
        parser.add_argument("--source", required=True)
        parser.add_argument("--name", help="Override the derived snippetName")
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Local source checkout; common sibling locations are searched when omitted",
    )
    parser.add_argument("--version", default="main", help="Output version folder")
    parser.add_argument("--language")
    parser.add_argument("--full-file", action="store_true")
    parser.add_argument(
        "--marker",
        help="Marker base; expands to <value>_START and <value>_END",
    )
    parser.add_argument("--start-marker", help="Exact start marker")
    parser.add_argument("--end-marker", help="Exact end marker")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add or edit cf-docs external snippets from a local source checkout"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_parser = subparsers.add_parser("add", help="Add and render a snippet")
    add_common_arguments(add_parser, editing=False)
    edit_parser = subparsers.add_parser(
        "edit", help="Edit and rerender a snippet without changing its name"
    )
    add_common_arguments(edit_parser, editing=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo = REPOS[args.repo]
    try:
        if args.command == "add":
            return add(args, repo)
        return edit(args, repo)
    except (OSError, SnippetAuthoringError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
