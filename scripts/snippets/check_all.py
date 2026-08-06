from __future__ import annotations

import argparse
from pathlib import Path

from . import build
from .validate import discover_pages


CF_DOCS_ROOT = Path(__file__).resolve().parents[2]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check every generated release-aware snippet page"
    )
    parser.add_argument(
        "paths", nargs="*", type=Path, default=[CF_DOCS_ROOT / "docs-main"]
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    pages = discover_pages(args.paths)
    failures = 0
    for page in pages:
        failures += build.main(["check", "--page", str(page), "--deployed"])
    if failures:
        print(f"{failures} of {len(pages)} generated snippet page(s) are stale")
        return 1
    print(f"Checked {len(pages)} generated snippet page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
