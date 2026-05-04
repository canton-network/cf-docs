from __future__ import annotations

import argparse
from pathlib import Path

from tests.harness.characterization_preview import (
    DEFAULT_PREVIEW_ROOT,
    build_characterization_preview_site,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a local Mintlify preview site for the checked-in x2mdx characterization fixtures."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_PREVIEW_ROOT,
        help="Directory where the preview site should be written.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    build_characterization_preview_site(args.output_dir)
    print(f"Wrote characterization preview site to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
