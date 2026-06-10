from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Sequence


DIRENV_ENV_MARKER = "DIGITAL_ASSET_DOCS_DIRENV"


def should_run_directly() -> bool:
    return (
        os.environ.get(DIRENV_ENV_MARKER) == "1"
        or bool(os.environ.get("IN_NIX_SHELL"))
        or shutil.which("direnv") is None
    )


def repo_direnv_command(repo_root: Path, *args: str) -> list[str]:
    if should_run_directly():
        if args and args[0] == "x2mdx":
            return ["python3", "-m", "x2mdx.cli", *args[1:]]
        return list(args)

    if args and args[0] == "x2mdx":
        return [
            "direnv",
            "exec",
            str(repo_root),
            "python3",
            "-m",
            "x2mdx.cli",
            *args[1:],
        ]

    return ["direnv", "exec", str(repo_root), *args]


def ensure_repo_direnv(*, repo_root: Path, script_path: Path, argv: Sequence[str]) -> None:
    if should_run_directly():
        return

    env = os.environ.copy()
    env[DIRENV_ENV_MARKER] = "1"
    command = repo_direnv_command(repo_root, "python3", str(script_path), *argv)
    raise SystemExit(subprocess.run(command, check=False, env=env).returncode)
