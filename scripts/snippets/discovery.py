from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

SOURCE_PAGE_SUFFIX = ".source.mdx"


def is_source_page(path: Path) -> bool:
    return path.name.endswith(SOURCE_PAGE_SUFFIX)


def discover_source_pages(paths: Iterable[Path]) -> list[Path]:
    """Return unique authored source pages in deterministic path order."""

    pages: set[Path] = set()
    for path in paths:
        if path.is_dir():
            pages.update(
                candidate.resolve()
                for candidate in path.rglob(f"*{SOURCE_PAGE_SUFFIX}")
                if candidate.is_file()
            )
        elif path.is_file() and is_source_page(path):
            pages.add(path.resolve())
    return sorted(pages)
