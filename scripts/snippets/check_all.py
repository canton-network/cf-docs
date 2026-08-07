from __future__ import annotations

import argparse
from pathlib import Path

from . import build
from .parser import load_registry, parse_page
from .validate import DEFAULT_REGISTRY, discover_pages

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
    repositories = load_registry(DEFAULT_REGISTRY)
    failures = 0
    for page in pages:
        parsed = parse_page(
            page.read_text(encoding="utf-8"),
            path=page,
            repositories=repositories,
        )
        command = ["check", "--page", str(page)]
        if parsed.conditions:
            command.append("--deployed")
        failures += build.main(command)
    if failures:
        print(f"{failures} of {len(pages)} generated snippet page(s) are stale")
        return 1
    print(f"Checked {len(pages)} generated snippet page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
