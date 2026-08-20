#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Sequence


REQUIRED_COMMANDS = (
    "awk",
    "bash",
    "curl",
    "direnv",
    "env",
    "find",
    "gh",
    "git",
    "grep",
    "gzip",
    "jar",
    "java",
    "javadoc",
    "mktemp",
    "node",
    "npm",
    "python3",
    "ruff",
    "sed",
    "sh",
    "sort",
    "tar",
    "tput",
    "unzip",
)
REQUIRED_PYTHON_MODULES = (
    "google.protobuf",
    "grpc_tools",
    "jinja2",
    "mypy",
    "pytest",
    "x2mdx.cli",
    "yaml",
)
NIX_STORE = Path("/nix/store")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that generated-doc runtime dependencies come from the project environment."
    )
    parser.add_argument(
        "--require-daml",
        action="store_true",
        help="Also require the dynamically installed DPM executable.",
    )
    return parser.parse_args()


def resolved_command(command: str) -> Path | None:
    path = shutil.which(command)
    return Path(path).resolve() if path else None


def is_nix_store_path(path: Path) -> bool:
    return path == NIX_STORE or NIX_STORE in path.parents


def missing_python_modules(modules: Sequence[str]) -> list[str]:
    missing: list[str] = []
    for module in modules:
        try:
            spec = importlib.util.find_spec(module)
        except (ImportError, ModuleNotFoundError, AttributeError):
            spec = None
        if spec is None:
            missing.append(module)
        else:
            print(f"python module {module}: available")
    return missing


def validate_commands(commands: Sequence[str]) -> list[str]:
    errors: list[str] = []
    for command in commands:
        path = resolved_command(command)
        if path is None:
            errors.append(f"missing command: {command}")
            continue
        print(f"command {command}: {path}")
        if not is_nix_store_path(path):
            errors.append(f"command is not supplied by the Nix environment: {command} -> {path}")
    return errors


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    if not os.environ.get("IN_NIX_SHELL"):
        errors.append("dependency check is not running inside a Nix shell")

    errors.extend(validate_commands(REQUIRED_COMMANDS))
    errors.extend(f"missing Python module: {module}" for module in missing_python_modules(REQUIRED_PYTHON_MODULES))

    if args.require_daml:
        dpm_path = resolved_command("dpm")
        if dpm_path is None:
            errors.append("missing dynamically installed command: dpm")
        else:
            print(f"dynamic command dpm: {dpm_path}")

    if errors:
        print("Generated-doc dependency check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Generated-doc dependency check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
