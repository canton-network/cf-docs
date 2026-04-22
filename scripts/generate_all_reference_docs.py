#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "x2mdx"
SCRIPT_PATHS = [
    REPO_ROOT / "scripts" / "generate_json_api_reference.py",
    REPO_ROOT / "scripts" / "generate_json_api_asyncapi_reference.py",
    REPO_ROOT / "scripts" / "generate_grpc_ledger_api_reference.py",
    REPO_ROOT / "scripts" / "generate_ledger_bindings_api_reference.py",
    REPO_ROOT / "scripts" / "generate_daml_standard_library_reference.py",
    REPO_ROOT / "scripts" / "generate_canton_protobuf_history.py",
    REPO_ROOT / "scripts" / "generate_wallet_gateway_openrpc_reference.py",
    REPO_ROOT / "scripts" / "generate_splice_scan_openapi_reference.py",
    REPO_ROOT / "scripts" / "generate_typescript_bindings_reference.py",
]
PARALLEL_EXTRA_ARGS: dict[str, list[str]] = {
    # The gRPC and protobuf wrappers both default to the same protobuf-history cache
    # tree, so parallel fanout needs a separate cache root for the gRPC wrapper.
    "generate_grpc_ledger_api_reference.py": [
        "--cache-dir",
        str(DEFAULT_CACHE_ROOT / "grpc-ledger-api-reference"),
        "--repo-dir",
        str(DEFAULT_CACHE_ROOT / "grpc-ledger-api-reference" / "repos" / "canton"),
    ],
}


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
    command = [sys.executable, str(script_path)]
    command.extend(PARALLEL_EXTRA_ARGS.get(script_path.name, []))
    return command


def main() -> int:
    args = parse_args()
    total = len(SCRIPT_PATHS)
    running_processes: list[tuple[Path, subprocess.Popen[bytes]]] = []

    for index, script_path in enumerate(SCRIPT_PATHS, start=1):
        command = build_command(script_path)
        print_banner(index=index, total=total, script_path=script_path)
        print("Command:", shlex.join(command), flush=True)
        if args.dry_run:
            continue

        running_processes.append((script_path, subprocess.Popen(command, cwd=REPO_ROOT)))

    if args.dry_run:
        print(f"\nDry run complete: {total} commands listed.", flush=True)
        return 0

    failures: list[tuple[Path, int]] = []
    for script_path, process in running_processes:
        return_code = process.wait()
        if return_code == 0:
            print(f"[{script_path.name}] completed successfully.", flush=True)
            continue
        print(f"[{script_path.name}] failed with exit code {return_code}.", flush=True)
        failures.append((script_path, return_code))

    if failures:
        failed_names = ", ".join(script_path.name for script_path, _return_code in failures)
        print(f"\nParallel reference-doc run finished with failures: {failed_names}", flush=True)
        return failures[0][1]

    print(f"\nCompleted {total} reference-doc generation steps in parallel.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
