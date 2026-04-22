from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence


DIRENV_ENV_MARKER = "DIGITAL_ASSET_DOCS_DIRENV"


def repo_direnv_command(repo_root: Path, *args: str) -> list[str]:
    return ["direnv", "exec", str(repo_root), *args]


def ensure_repo_direnv(*, repo_root: Path, script_path: Path, argv: Sequence[str]) -> None:
    if os.environ.get(DIRENV_ENV_MARKER) == "1":
        return

    env = os.environ.copy()
    env[DIRENV_ENV_MARKER] = "1"
    command = repo_direnv_command(repo_root, "python3", str(script_path), *argv)
    raise SystemExit(subprocess.run(command, check=False, env=env).returncode)
