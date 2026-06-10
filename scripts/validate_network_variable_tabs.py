from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def git_status() -> set[str]:
    status = run(["git", "status", "--porcelain=v1"])
    if status.returncode:
        if status.stderr:
            print(status.stderr, end="", file=sys.stderr)
        raise SystemExit(status.returncode)
    return set(status.stdout.splitlines())


def main() -> None:
    before_status = git_status()

    generate = run(["python3", "scripts/generate_network_variable_tabs.py"])
    if generate.stdout:
        print(generate.stdout, end="")
    if generate.stderr:
        print(generate.stderr, end="", file=sys.stderr)
    if generate.returncode:
        raise SystemExit(generate.returncode)

    after_status = git_status()
    new_changes = sorted(after_status - before_status)
    if not new_changes:
        print("Network variable tabs are rendered and up to date.")
        return

    print(
        "Network variable tabs are stale. Run `npm run generate:network-variable-tabs` "
        "and commit the rendered MDX changes.",
        file=sys.stderr,
    )
    print("\n".join(new_changes), file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
