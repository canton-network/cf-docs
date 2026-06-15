#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPENAPI_ROOT = REPO_ROOT / "docs-main" / "openapi"
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def mintlify_operation_slug(summary: str) -> str:
    without_braced_params = re.sub(r"\{[^}]+}", "", summary)
    return re.sub(r"[^A-Za-z0-9]+", "", without_braced_params).lower()


def operation_slug_collisions(openapi_path: Path) -> list[str]:
    spec = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError(f"Expected OpenAPI spec to parse as an object: {openapi_path}")

    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return []

    slugs: dict[str, list[str]] = {}
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            summary = operation.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                continue
            slug = mintlify_operation_slug(summary)
            slugs.setdefault(slug, []).append(f"{method.upper()} {path}")

    return [
        f"{openapi_path}: {slug}: {', '.join(operations)}"
        for slug, operations in slugs.items()
        if len(operations) > 1
    ]


def openapi_files(root: Path) -> list[Path]:
    return sorted(
        path
        for pattern in ("*.yaml", "*.yml")
        for path in root.rglob(pattern)
        if path.is_file()
    )


def validate_roots(roots: list[Path]) -> None:
    failures: list[str] = []
    checked = 0
    for root in roots:
        paths = openapi_files(root) if root.is_dir() else [root]
        for path in paths:
            checked += 1
            failures.extend(operation_slug_collisions(path))

    if failures:
        details = "\n".join(f"- {failure}" for failure in failures)
        raise ValueError(
            "OpenAPI specs contain operations that collide under Mintlify operation slugging.\n"
            f"{details}"
        )
    print(f"Validated Mintlify OpenAPI operation slugs for {checked} specs.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate OpenAPI operation summaries do not collide under Mintlify operation slugging."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=[str(DEFAULT_OPENAPI_ROOT)],
        help="OpenAPI files or directories to validate. Defaults to docs-main/openapi.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validate_roots([Path(path).resolve() for path in args.paths])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
