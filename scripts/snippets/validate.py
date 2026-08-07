from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .model import Diagnostic, SnippetValidationError
from .parser import load_registry, parse_page

CF_DOCS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = CF_DOCS_ROOT / "config" / "snippet-repositories.json"


def discover_pages(paths: list[Path]) -> list[Path]:
    pages: list[Path] = []
    for path in paths:
        if path.is_dir():
            pages.extend(path.rglob("*.source.mdx"))
        elif path.is_file():
            pages.append(path)
    return sorted({page.resolve() for page in pages})


def validate_pages(
    paths: list[Path], registry_path: Path, *, allow_local: bool = False
) -> list[Diagnostic]:
    repositories = load_registry(registry_path)
    diagnostics: list[Diagnostic] = []
    for page in discover_pages(paths):
        try:
            parse_page(
                page.read_text(encoding="utf-8"),
                path=page,
                repositories=repositories,
                allow_local=allow_local,
            )
        except SnippetValidationError as error:
            diagnostics.extend(error.diagnostics)
    return diagnostics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate inline snippet declarations in authored MDX"
    )
    parser.add_argument(
        "paths", nargs="*", type=Path, default=[CF_DOCS_ROOT / "docs-main"]
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--allow-local",
        action="store_true",
        help="Allow preview-only local:// references",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    diagnostics = validate_pages(
        args.paths, args.registry, allow_local=args.allow_local
    )
    if diagnostics:
        for diagnostic in diagnostics:
            print(diagnostic.format(), file=sys.stderr)
        return 1
    pages = discover_pages(args.paths)
    print(f"Validated {len(pages)} authored snippet page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
