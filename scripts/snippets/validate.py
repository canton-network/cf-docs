from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .discovery import discover_source_pages
from .file_validation import validate_authored_files

CF_DOCS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = CF_DOCS_ROOT / "config" / "snippet-repositories.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate release-aware declarations in authored MDX"
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
    diagnostics = validate_authored_files(
        args.paths,
        registry_path=args.registry,
        allow_local=args.allow_local,
    )
    if diagnostics:
        for diagnostic in diagnostics:
            print(diagnostic.format(), file=sys.stderr)
        return 1
    print(f"Validated {len(discover_source_pages(args.paths))} authored snippet page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
