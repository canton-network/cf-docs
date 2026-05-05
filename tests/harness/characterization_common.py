from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CHARACTERIZATION_ROOT = REPO_ROOT / "tests" / "fixtures" / "characterization"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def reset_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def relative_to_manifest(target: Path, manifest_path: Path) -> str:
    return Path(os.path.relpath(target.resolve(), start=manifest_path.resolve().parent)).as_posix()


def run(command: list[str], *, cwd: Path = REPO_ROOT, env: dict[str, str] | None = None) -> None:
    print("Running:", " ".join(command))
    combined_env = os.environ.copy()
    if env:
        combined_env.update(env)
    subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        env=combined_env,
    )


def run_x2mdx(args: list[str]) -> None:
    env = os.environ.copy()
    pythonpath_entries = [str(REPO_ROOT / "src")]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    run([sys.executable, "-m", "x2mdx.cli", *args], env=env)
