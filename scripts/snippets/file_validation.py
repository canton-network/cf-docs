from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .discovery import discover_source_pages
from .model import Diagnostic
from .page_validation import validate_authored_page
from .registry import load_repository_registry


def validate_authored_files(
    paths: Iterable[Path],
    *,
    registry_path: Path,
    allow_local: bool = False,
) -> tuple[Diagnostic, ...]:
    """Validate discovered source pages against one checked-in registry."""

    registry = load_repository_registry(registry_path)
    diagnostics: list[Diagnostic] = []
    for page in discover_source_pages(paths):
        result = validate_authored_page(
            page.read_text(encoding="utf-8"),
            path=page,
            registry=registry,
            allow_local=allow_local,
        )
        diagnostics.extend(result.diagnostics)
    return tuple(
        sorted(
            diagnostics,
            key=lambda diagnostic: (
                str(diagnostic.path),
                diagnostic.span.start,
                diagnostic.code,
            ),
        )
    )
