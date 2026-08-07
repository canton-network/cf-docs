from __future__ import annotations

from pathlib import Path

from scripts.snippets.discovery import discover_source_pages


def test_discovers_source_pages_recursively_in_path_order(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    nested = docs / "nested"
    nested.mkdir(parents=True)
    second = docs / "second.source.mdx"
    first = nested / "first.source.mdx"
    ignored = nested / "ordinary.mdx"
    second.write_text("second", encoding="utf-8")
    first.write_text("first", encoding="utf-8")
    ignored.write_text("ignored", encoding="utf-8")

    assert discover_source_pages([docs]) == sorted(
        [first.resolve(), second.resolve()]
    )


def test_accepts_explicit_source_page_and_deduplicates_it(tmp_path: Path) -> None:
    page = tmp_path / "page.source.mdx"
    page.write_text("page", encoding="utf-8")

    assert discover_source_pages([tmp_path, page]) == [page.resolve()]


def test_ignores_explicit_non_source_files_and_missing_paths(tmp_path: Path) -> None:
    ordinary_page = tmp_path / "page.mdx"
    ordinary_page.write_text("page", encoding="utf-8")

    assert discover_source_pages([ordinary_page, tmp_path / "missing"]) == []
