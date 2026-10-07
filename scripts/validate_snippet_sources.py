#!/usr/bin/env python3
"""Validate remote snippet configs against local source-repo checkouts.

Examples:
  python3 scripts/validate_snippet_sources.py
  python3 scripts/validate_snippet_sources.py daml --source-dir ../daml
  python3 scripts/validate_snippet_sources.py canton --source-dir ../canton-new-2
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from generate_external_snippets import REPOS, SnippetRepo, find_source_dir


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config" / "snippet-config"
REMOTE_LISTS_FILE = "remote-snippet-lists.json"
ERROR_LOG_NAME = "snippet-source-errors.log"


@dataclass(frozen=True)
class SourceError:
    repo: str
    snippet_name: str
    message: str

    def format(self) -> str:
        name = self.snippet_name or "(repo)"
        return f"{self.repo} {name}: {self.message}"


@dataclass(frozen=True)
class AuditResult:
    snippet_count: int
    repo_count: int
    errors: tuple[SourceError, ...]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repo",
        nargs="?",
        help="Only validate this remote snippet repo (e.g. daml, canton, splice). "
        "Omit to check every repo in remote-snippet-lists.json.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print source validation errors.",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Exit 0 even when source validation errors are found.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Directory for snippet-source-errors.log (default: repo root).",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Path to the git checkout for the selected repo. Required with a repo name "
        "if autodiscovery cannot find a unique checkout.",
    )
    return parser.parse_args(argv)


def repo_name_from_config_filename(filename: str) -> str:
    suffix = "-snippet-list-remote.json"
    if filename.endswith(suffix):
        return filename[: -len(suffix)]
    return Path(filename).stem


def load_remote_list_files(config_dir: Path = CONFIG_DIR) -> list[str]:
    path = config_dir / REMOTE_LISTS_FILE
    payload = json.loads(path.read_text(encoding="utf-8"))
    lists = payload.get("snippetLists")
    if not isinstance(lists, list) or not lists:
        raise SystemExit(f"No snippetLists found in {path}")
    return [str(name) for name in lists]


def load_snippets(config_path: Path) -> list[dict]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    snippets = payload.get("snippets", [])
    if not isinstance(snippets, list):
        raise SystemExit(f"Expected snippets array in {config_path}")
    return snippets


def resolve_repo_key(name: str) -> str:
    lowered = name.lower()
    if lowered in REPOS:
        return lowered
    for key, repo in REPOS.items():
        if lowered in {alias.lower() for alias in repo.aliases}:
            return key
    return lowered


def selected_repo_files(
    *,
    config_dir: Path,
    repo: str | None,
) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for filename in load_remote_list_files(config_dir):
        repo_key = resolve_repo_key(repo_name_from_config_filename(filename))
        files.append((repo_key, config_dir / filename))
    if repo is None:
        return files
    wanted = resolve_repo_key(repo)
    matched = [(key, path) for key, path in files if key == wanted]
    if not matched:
        available = ", ".join(key for key, _ in files)
        raise SystemExit(f"Unknown snippet repo {repo!r}. Available: {available}")
    return matched


def split_lines(content: str) -> list[str]:
    return content.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def validate_lines(location: dict, line_count: int) -> str | None:
    try:
        start = int(location["start"])
        end = int(location["end"])
    except (KeyError, TypeError, ValueError):
        return "invalid line range: start/end must be integers"
    if start < 1 or end < 1:
        return f"line range {start}-{end} is invalid (lines are 1-based)"
    if start > end:
        return f"line range {start}-{end} is invalid (start must be <= end)"
    if start > line_count or end > line_count:
        return f"line range {start}-{end} is out of bounds (file has {line_count} lines)"
    return None


def validate_string_markers(location: dict, content: str) -> str | None:
    start = location.get("start")
    end = location.get("end")
    if not start or not end:
        return "stringMarker requires start and end markers"
    start_index = content.find(str(start))
    if start_index < 0:
        return f"start marker not found: {start!r}"
    newline = content.find("\n", start_index)
    content_start = newline + 1 if newline >= 0 else start_index + len(str(start))
    if content.find(str(end), content_start) < 0:
        return f"end marker not found: {end!r}"
    return None


def validate_json_index(location: dict, content: str) -> str | None:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        return f"file is not valid JSON: {error.msg}"
    if not isinstance(payload, list):
        return "JSON root must be an array for location type jsonIndex"
    try:
        start = int(location["start"])
        end = int(location.get("end", location["start"]))
    except (KeyError, TypeError, ValueError):
        return "invalid jsonIndex range: start/end must be integers"
    length = len(payload)
    if start < 0 or end < 0 or start >= length or end >= length:
        return f"jsonIndex {start}-{end} is out of bounds (array length {length})"
    if start > end:
        return f"jsonIndex {start}-{end} is invalid (start must be <= end)"
    return None


def validate_regex_wrap(location: dict, content: str) -> str | None:
    import re

    start = location.get("start")
    end = location.get("end")
    if not start or not end:
        return "regexWrap requires start and end patterns"
    start_match = re.search(str(start), content)
    if start_match is None:
        return f"start regex not found: {start!r}"
    remaining = content[start_match.end() :]
    if re.search(str(end), remaining) is None:
        return f"end regex not found: {end!r}"
    return None


def validate_location(location: dict | None, content: str) -> str | None:
    if not location or not location.get("type"):
        return "missing location type"
    location_type = str(location["type"])
    if location_type == "fullFile":
        return None
    if location_type == "lines":
        return validate_lines(location, len(split_lines(content)))
    if location_type == "stringMarker":
        return validate_string_markers(location, content)
    if location_type == "jsonIndex":
        return validate_json_index(location, content)
    if location_type == "regexWrap":
        return validate_regex_wrap(location, content)
    return f"unsupported location type: {location_type}"


def validate_snippet(snippet: dict, source_dir: Path) -> str | None:
    source_filepath = str(snippet.get("sourceFilepath") or "").lstrip("/")
    if not source_filepath:
        return "missing sourceFilepath"
    source_path = source_dir / source_filepath
    if not source_path.is_file():
        return f"source file not found: {source_filepath}"
    content = source_path.read_text(encoding="utf-8")
    return validate_location(snippet.get("location"), content)


def resolve_source_dirs(
    repo_keys: list[str],
    source_dir: Path | None,
) -> tuple[dict[str, Path], list[SourceError]]:
    resolved: dict[str, Path] = {}
    errors: list[SourceError] = []
    unique_keys = list(dict.fromkeys(repo_keys))
    if source_dir is not None:
        if len(unique_keys) != 1:
            raise SystemExit("Pass a repo name when using --source-dir.")
        path = source_dir.expanduser().resolve()
        if not path.is_dir():
            raise SystemExit(f"Source directory does not exist: {path}")
        resolved[unique_keys[0]] = path
        return resolved, errors

    for key in unique_keys:
        repo = REPOS.get(key)
        if repo is None:
            repo = SnippetRepo(name=key, config_name="", aliases=(key,))
        try:
            resolved[key] = find_source_dir(repo, None)
        except SystemExit as error:
            errors.append(
                SourceError(repo=key, snippet_name="", message=str(error))
            )
    return resolved, errors


def audit(
    *,
    config_dir: Path = CONFIG_DIR,
    repo: str | None = None,
    source_dir: Path | None = None,
) -> AuditResult:
    repo_files = selected_repo_files(config_dir=config_dir, repo=repo)
    source_dirs, errors = resolve_source_dirs(
        [key for key, _ in repo_files],
        source_dir,
    )
    snippet_count = 0
    for repo_key, config_path in repo_files:
        if not config_path.is_file():
            errors.append(
                SourceError(
                    repo=repo_key,
                    snippet_name="",
                    message=f"missing config file: {config_path.name}",
                )
            )
            continue
        snippets = load_snippets(config_path)
        checkout = source_dirs.get(repo_key)
        if checkout is None:
            continue
        for snippet in snippets:
            snippet_count += 1
            name = str(snippet.get("snippetName") or "")
            message = validate_snippet(snippet, checkout)
            if message:
                errors.append(SourceError(repo=repo_key, snippet_name=name, message=message))
    return AuditResult(
        snippet_count=snippet_count,
        repo_count=len(repo_files),
        errors=tuple(errors),
    )


def write_log(path: Path, errors: tuple[SourceError, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if errors:
        path.write_text("\n".join(error.format() for error in errors) + "\n", encoding="utf-8")
    else:
        path.write_text("", encoding="utf-8")


def print_report(result: AuditResult, quiet: bool) -> None:
    stream = sys.stderr if quiet else sys.stdout
    if not quiet:
        print(
            f"Checked {result.snippet_count} snippets across {result.repo_count} repos; "
            f"{len(result.errors)} errors.",
            file=stream,
        )
        if not result.errors:
            print("All remote snippet sources are valid.", file=stream)
            return
    if result.errors:
        print("Snippet source errors:", file=stream)
        for error in result.errors:
            print(error.format(), file=stream)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = audit(
        config_dir=CONFIG_DIR,
        repo=args.repo,
        source_dir=args.source_dir,
    )
    output_dir = args.output_path.resolve() if args.output_path else REPO_ROOT
    write_log(output_dir / ERROR_LOG_NAME, result.errors)
    print_report(result, quiet=args.quiet)
    if result.errors and not args.no_fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
