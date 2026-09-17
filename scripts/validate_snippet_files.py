#!/usr/bin/env python3
"""Audit snippet imports in docs-main content pages."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_MAIN = REPO_ROOT / "docs-main"
SNIPPETS_ROOT = DOCS_MAIN / "snippets"

IMPORT_RE = re.compile(
    r"^\s*import\s+(?:[A-Za-z_$][\w$]*|\*\s+as\s+[A-Za-z_$][\w$]*|\{[^}]+\})\s+"
    r"from\s+[\"'](?P<path>[^\"']+)[\"']\s*;?\s*$",
    re.MULTILINE,
)
NETWORKVARS_SOURCE_RE = re.compile(
    r"\{/\*\s*NETWORKVARS_START\s+source=\"(?P<source>[^\"]+)\"\s*\*/\}"
)

MISSING_LOG_NAME = "snippets-missing.log"
ORPHAN_LOG_NAME = "snippets-orphan.log"


@dataclass(frozen=True)
class AuditResult:
    content_pages: int
    referenced: frozenset[str]
    existing: frozenset[str]
    missing: tuple[str, ...]
    orphans: tuple[str, ...]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print errors (missing or orphan snippets).",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Exit 0 even when missing or orphan snippets are found.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Directory for snippets-missing.log and snippets-orphan.log (default: repo root).",
    )
    parser.add_argument(
        "--delete-orphan-snippets",
        action="store_true",
        help="After writing snippets-orphan.log, delete orphan snippet files.",
    )
    return parser.parse_args(argv)


def content_pages(docs_main: Path = DOCS_MAIN, snippets_root: Path = SNIPPETS_ROOT) -> list[Path]:
    return sorted(
        path
        for path in docs_main.rglob("*.mdx")
        if snippets_root not in path.parents and path.is_file()
    )


def existing_snippets(snippets_root: Path = SNIPPETS_ROOT, docs_main: Path = DOCS_MAIN) -> set[str]:
    if not snippets_root.is_dir():
        return set()
    return {
        snippet_ref_for_path(path, docs_main)
        for path in snippets_root.rglob("*.mdx")
        if path.is_file()
    }


def snippet_ref_for_path(path: Path, docs_main: Path = DOCS_MAIN) -> str:
    return "/" + path.relative_to(docs_main).as_posix()


def resolve_snippet_ref(snippet_ref: str, docs_main: Path = DOCS_MAIN) -> Path:
    if snippet_ref.startswith("/"):
        return docs_main / snippet_ref.removeprefix("/")
    return docs_main / snippet_ref


def normalize_snippet_ref(path: str) -> str | None:
    if not path.startswith("/snippets/"):
        return None
    if not path.endswith(".mdx"):
        path = f"{path}.mdx"
    return path


def snippet_refs_in_text(text: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for match in IMPORT_RE.finditer(text):
        ref = normalize_snippet_ref(match.group("path"))
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    for match in NETWORKVARS_SOURCE_RE.findall(text):
        ref = normalize_snippet_ref(match)
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def collect_referenced_snippets(
    pages: list[Path],
    docs_main: Path = DOCS_MAIN,
) -> set[str]:
    referenced: set[str] = set()
    queue: list[str] = []

    def add_ref(ref: str) -> None:
        if ref not in referenced:
            referenced.add(ref)
            queue.append(ref)

    for page in pages:
        text = page.read_text(encoding="utf-8")
        for ref in snippet_refs_in_text(text):
            add_ref(ref)

    while queue:
        ref = queue.pop()
        snippet_path = resolve_snippet_ref(ref, docs_main)
        if not snippet_path.is_file():
            continue
        nested_text = snippet_path.read_text(encoding="utf-8")
        for nested_ref in snippet_refs_in_text(nested_text):
            add_ref(nested_ref)

    return referenced


def audit(
    docs_main: Path = DOCS_MAIN,
    snippets_root: Path = SNIPPETS_ROOT,
) -> AuditResult:
    pages = content_pages(docs_main, snippets_root)
    referenced = collect_referenced_snippets(pages, docs_main)
    existing = existing_snippets(snippets_root, docs_main)
    missing = tuple(sorted(referenced - existing))
    orphans = tuple(sorted(existing - referenced))
    return AuditResult(
        content_pages=len(pages),
        referenced=frozenset(referenced),
        existing=frozenset(existing),
        missing=missing,
        orphans=orphans,
    )


def write_log(path: Path, entries: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if entries:
        path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    else:
        path.write_text("", encoding="utf-8")


def delete_orphan_snippets(orphans: tuple[str, ...], docs_main: Path = DOCS_MAIN) -> list[str]:
    deleted: list[str] = []
    for ref in orphans:
        path = resolve_snippet_ref(ref, docs_main)
        if not path.is_file():
            continue
        try:
            path.relative_to(docs_main / "snippets")
        except ValueError:
            continue
        path.unlink()
        deleted.append(ref)
    return deleted


def print_report(result: AuditResult, quiet: bool) -> None:
    has_errors = bool(result.missing or result.orphans)
    stream = sys.stderr if quiet else sys.stdout
    if not quiet:
        print(
            f"Scanned {result.content_pages} content pages; "
            f"{len(result.referenced)} referenced snippets; "
            f"{len(result.existing)} snippet files.",
            file=stream,
        )
        print(f"Missing snippets: {len(result.missing)}", file=stream)
        print(f"Orphan snippets: {len(result.orphans)}", file=stream)
        if not has_errors:
            print(
                "All referenced snippets exist and all snippet files are linked.",
                file=stream,
            )
            return

    if result.missing:
        print("Missing snippets:", file=stream)
        for ref in result.missing:
            print(ref, file=stream)
    if result.orphans:
        print("Orphan snippets:", file=stream)
        for ref in result.orphans:
            print(ref, file=stream)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = audit(docs_main=DOCS_MAIN, snippets_root=SNIPPETS_ROOT)
    output_dir = args.output_path.resolve() if args.output_path else REPO_ROOT
    write_log(output_dir / MISSING_LOG_NAME, result.missing)
    write_log(output_dir / ORPHAN_LOG_NAME, result.orphans)
    if args.delete_orphan_snippets and result.orphans:
        deleted = delete_orphan_snippets(result.orphans, docs_main=DOCS_MAIN)
        if not args.quiet:
            print(f"Deleted {len(deleted)} orphan snippet files.")
    print_report(result, quiet=args.quiet)
    if (result.missing or result.orphans) and not args.no_fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
