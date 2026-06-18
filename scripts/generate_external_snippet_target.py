#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "generated-docs" / "external-snippet-sources.json"
DEFAULT_CACHE_DIR = REPO_ROOT / ".internal" / "cache" / "external-snippets"


@dataclass(frozen=True)
class ExternalSnippetSource:
    key: str
    label: str
    repository: str
    ref: str
    version: str
    repo_arg: str
    output_path: str
    requires_docker: bool = False
    skip_if_unavailable: bool = False


class SourceUnavailableError(RuntimeError):
    pass


def load_sources(config_path: Path) -> tuple[ExternalSnippetSource, ...]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    items = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError(f"Expected sources list in {config_path}")
    sources: list[ExternalSnippetSource] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            sources.append(
                ExternalSnippetSource(
                    key=str(item["key"]),
                    label=str(item["label"]),
                    repository=str(item["repository"]),
                    ref=str(item["ref"]),
                    version=str(item["version"]),
                    repo_arg=str(item["repo_arg"]),
                    output_path=str(item["output_path"]),
                    requires_docker=bool(item.get("requires_docker", False)),
                    skip_if_unavailable=bool(item.get("skip_if_unavailable", False)),
                )
            )
        except KeyError as error:
            raise ValueError(f"External snippet source missing field {error.args[0]!r}: {item}") from error
    return tuple(sources)


def source_by_key(config_path: Path, key: str) -> ExternalSnippetSource:
    for source in load_sources(config_path):
        if source.key == key:
            return source
    raise SystemExit(f"Unknown external snippet source {key!r}")


def run(command: list[str], *, cwd: Path, dry_run: bool = False) -> str:
    print("$ " + " ".join(command))
    if dry_run:
        return ""
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    return completed.stdout.strip()


def clone_url(repository: str) -> str:
    return f"https://github.com/{repository}.git"


def source_dir(cache_dir: Path, source: ExternalSnippetSource) -> Path:
    return cache_dir / source.key / "repo"


def ensure_source_available(source: ExternalSnippetSource, *, dry_run: bool) -> None:
    if dry_run:
        return
    try:
        run(
            ["git", "ls-remote", "--exit-code", clone_url(source.repository), source.ref],
            cwd=REPO_ROOT,
            dry_run=False,
        )
    except subprocess.CalledProcessError as error:
        raise SourceUnavailableError(
            f"{source.label} source {source.repository}@{source.ref} is not available to this runner"
        ) from error


def ensure_checkout(source: ExternalSnippetSource, *, cache_dir: Path, dry_run: bool) -> Path:
    ensure_source_available(source, dry_run=dry_run)
    checkout = source_dir(cache_dir, source)
    if not dry_run:
        checkout.parent.mkdir(parents=True, exist_ok=True)
    if not (checkout / ".git").exists():
        run(["git", "clone", clone_url(source.repository), str(checkout)], cwd=REPO_ROOT, dry_run=dry_run)
    run(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "fetch", "origin"], cwd=checkout, dry_run=dry_run)
    run(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "checkout", source.ref], cwd=checkout, dry_run=dry_run)
    run(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "reset", "--hard", source.ref], cwd=checkout, dry_run=dry_run)
    run(["git", "clean", "-ffd"], cwd=checkout, dry_run=dry_run)
    return checkout


def allow_direnv(checkout: Path, *, dry_run: bool) -> None:
    if not (checkout / ".envrc").is_file() or not shutil.which("direnv"):
        return
    run(["direnv", "allow"], cwd=checkout, dry_run=dry_run)


def check_docker(source: ExternalSnippetSource, *, dry_run: bool) -> None:
    if not source.requires_docker:
        return
    run(["docker", "info", "--format", "{{.ServerVersion}}"], cwd=REPO_ROOT, dry_run=dry_run)


def generate_source(source: ExternalSnippetSource, *, cache_dir: Path, dry_run: bool) -> None:
    try:
        checkout = ensure_checkout(source, cache_dir=cache_dir, dry_run=dry_run)
    except SourceUnavailableError as error:
        if source.skip_if_unavailable:
            print(f"Skipping {source.key}: {error}")
            return
        raise
    allow_direnv(checkout, dry_run=dry_run)
    check_docker(source, dry_run=dry_run)
    run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_external_snippets.py"),
            source.repo_arg,
            "--source-dir",
            str(checkout),
            "--copy-output",
            "--replace-output",
            "--version",
            source.version,
            "--fetch",
        ],
        cwd=REPO_ROOT,
        dry_run=dry_run,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one configured external snippet output tree.")
    parser.add_argument("--source-key", required=True, help="External snippet source key from the manifest.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Print clone/generation commands without running them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = source_by_key(args.config, args.source_key)
    generate_source(source, cache_dir=args.cache_dir, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
