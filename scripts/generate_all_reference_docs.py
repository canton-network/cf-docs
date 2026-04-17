#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATHS = [
    REPO_ROOT / "scripts" / "generate_json_api_reference.py",
    REPO_ROOT / "scripts" / "generate_json_api_asyncapi_reference.py",
    REPO_ROOT / "scripts" / "generate_ledger_bindings_api_reference.py",
    REPO_ROOT / "scripts" / "generate_daml_standard_library_reference.py",
    REPO_ROOT / "scripts" / "generate_canton_protobuf_history.py",
    REPO_ROOT / "scripts" / "generate_wallet_gateway_openrpc_reference.py",
    REPO_ROOT / "scripts" / "generate_typescript_bindings_reference.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run every generated reference-doc wrapper in sequence from the docs repo."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without executing them.",
    )
    return parser.parse_args()


def print_banner(*, index: int, total: int, script_path: Path) -> None:
    title = f"[{index}/{total}] {script_path.name}"
    print(f"\n=== {title} ===", flush=True)


def build_command(script_path: Path) -> list[str]:
    return [sys.executable, str(script_path)]


def main() -> int:
    args = parse_args()
    total = len(SCRIPT_PATHS)

    for index, script_path in enumerate(SCRIPT_PATHS, start=1):
        command = build_command(script_path)
        print_banner(index=index, total=total, script_path=script_path)
        print("Command:", shlex.join(command), flush=True)
        if args.dry_run:
            continue

        completed = subprocess.run(command, cwd=REPO_ROOT)
        if completed.returncode != 0:
            return completed.returncode

    if args.dry_run:
        print(f"\nDry run complete: {total} commands listed.", flush=True)
    else:
        print(f"\nCompleted {total} reference-doc generation steps.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
