#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import summarize_version_changes


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class UpdateSurface:
    key: str
    title: str
    branch: str
    description: str
    generate_commands: tuple[tuple[str, ...], ...]
    paths: tuple[str, ...]
    summary_kind: str
    summary_path: str
    summary_label: str | None
    validation: tuple[str, ...]


SURFACES = (
    UpdateSurface(
        key="version-dashboard",
        title="Update version dashboard data",
        branch="version-dashboard/update",
        description=(
            "Updates the committed Canton Network version dashboard data from public network, "
            "package, and installer sources."
        ),
        generate_commands=(("nix-shell", "--run", "npm run generate:version-compatibility-dashboard"),),
        paths=(
            "config/repo-version-config.json",
            "docs-main/snippets/generated/version-dashboard-data.mdx",
        ),
        summary_kind="dashboard",
        summary_path="config/repo-version-config.json",
        summary_label=None,
        validation=(
            "npm run generate:version-compatibility-dashboard",
            "git diff --check",
        ),
    ),
    UpdateSurface(
        key="wallet-gateway-openrpc",
        title="Update Wallet Gateway OpenRPC reference",
        branch="generated-references/wallet-gateway-openrpc/update",
        description=(
            "Updates the Wallet Gateway OpenRPC source pin to the latest stable "
            "wallet-gateway-remote release and regenerates the checked-in Wallet Gateway "
            "OpenRPC reference pages."
        ),
        generate_commands=(
            ("nix-shell", "--run", "npm run update:generated-reference-sources -- --source wallet-gateway-openrpc"),
            ("nix-shell", "--run", "npm run generate:wallet-gateway-openrpc-reference"),
        ),
        paths=(
            "config/x2mdx/wallet-gateway-openrpc/source-artifacts.json",
            "docs-main/docs.json",
            "docs-main/reference/wallet-gateway-json-rpc",
        ),
        summary_kind="source-config",
        summary_path="config/x2mdx/wallet-gateway-openrpc/source-artifacts.json",
        summary_label="Wallet Gateway OpenRPC",
        validation=(
            "npm run update:generated-reference-sources -- --source wallet-gateway-openrpc",
            "npm run generate:wallet-gateway-openrpc-reference",
            "git diff --check",
        ),
    ),
)


def generated_clean_paths() -> tuple[str, ...]:
    paths = {".internal"}
    for surface in SURFACES:
        paths.update(surface.paths)
    return tuple(sorted(paths))


def run(command: Sequence[str], *, capture: bool = False) -> str:
    kwargs: dict[str, object] = {
        "cwd": REPO_ROOT,
        "check": True,
        "text": True,
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
    completed = subprocess.run(list(command), **kwargs)
    return completed.stdout.strip() if capture else ""


def git(*args: str, capture: bool = False) -> str:
    return run(("git", *args), capture=capture)


def gh(*args: str, capture: bool = False) -> str:
    return run(("gh", *args), capture=capture)


def base_branch_from_environment() -> str:
    base_branch = os.environ.get("PR_BASE_BRANCH") or os.environ.get("GITHUB_REF_NAME")
    if not base_branch:
        raise RuntimeError("PR_BASE_BRANCH or GITHUB_REF_NAME must be set")
    return base_branch


def repository_from_environment() -> str:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        raise RuntimeError("GITHUB_REPOSITORY must be set")
    return repository


def body_markdown(*, surface: UpdateSurface, changes: list[str]) -> str:
    change_text = "\n".join(changes) if changes else "- No version values changed."
    validation = "\n".join(f"- `{command}`" for command in surface.validation)
    return (
        f"{surface.description}\n\n"
        f"Version changes:\n"
        f"{change_text}\n\n"
        f"Validation run by the workflow:\n"
        f"{validation}\n"
    )


def summarize_surface_changes(surface: UpdateSurface, before_path: Path) -> list[str]:
    after_path = REPO_ROOT / surface.summary_path
    if surface.summary_kind == "dashboard":
        return summarize_version_changes.dashboard_changes(before_path, after_path)
    if surface.summary_kind == "source-config":
        if surface.summary_label is None:
            raise ValueError(f"Surface {surface.key} must define summary_label")
        return summarize_version_changes.source_config_changes(
            before_path,
            after_path,
            label=surface.summary_label,
        )
    raise ValueError(f"Unknown summary kind for {surface.key}: {surface.summary_kind}")


def reset_to_base(base_sha: str) -> None:
    git("switch", "--detach", base_sha)
    git("reset", "--hard", base_sha)
    git("clean", "-fd", "--", *generated_clean_paths())


def write_base_file(base_sha: str, relative_path: str) -> Path:
    before = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
    before_path = Path(before.name)
    before.write(git("show", f"{base_sha}:{relative_path}", capture=True))
    before.close()
    return before_path


def has_surface_changes(surface: UpdateSurface) -> bool:
    output = git("status", "--porcelain", "--", *surface.paths, capture=True)
    return bool(output)


def push_branch(branch: str) -> None:
    remote_output = git("ls-remote", "--heads", "origin", branch, capture=True)
    remote_sha = remote_output.split()[0] if remote_output else ""
    if remote_sha:
        git("push", f"--force-with-lease=refs/heads/{branch}:{remote_sha}", "origin", f"HEAD:{branch}")
    else:
        git("push", "origin", f"HEAD:{branch}")


def create_or_update_pull_request(
    *,
    surface: UpdateSurface,
    body_path: Path,
    base_branch: str,
    repository: str,
) -> None:
    if not has_surface_changes(surface):
        print(f"No changes for {surface.title}")
        return

    git("status", "--short", "--", *surface.paths)
    git("switch", "-c", surface.branch)
    git("add", "--", *surface.paths)
    git("diff", "--cached", "--stat")
    git("diff", "--cached", "--check")
    git("commit", "-m", surface.title)
    push_branch(surface.branch)

    existing_pr_number = gh(
        "pr",
        "list",
        "--repo",
        repository,
        "--head",
        surface.branch,
        "--base",
        base_branch,
        "--state",
        "open",
        "--json",
        "number",
        "--jq",
        ".[0].number // empty",
        capture=True,
    )
    if existing_pr_number:
        gh(
            "pr",
            "edit",
            existing_pr_number,
            "--repo",
            repository,
            "--title",
            surface.title,
            "--body-file",
            str(body_path),
        )
        subprocess.run(
            [
                "gh",
                "pr",
                "ready",
                existing_pr_number,
                "--repo",
                repository,
                "--undo",
            ],
            cwd=REPO_ROOT,
            check=False,
        )
        return

    gh(
        "pr",
        "create",
        "--base",
        base_branch,
        "--head",
        surface.branch,
        "--repo",
        repository,
        "--draft",
        "--title",
        surface.title,
        "--body-file",
        str(body_path),
    )


def process_surface(*, surface: UpdateSurface, base_sha: str, base_branch: str, repository: str) -> None:
    reset_to_base(base_sha)
    before_path = write_base_file(base_sha, surface.summary_path)

    for command in surface.generate_commands:
        run(command)

    changes = summarize_surface_changes(surface, before_path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as body_file:
        body_path = Path(body_file.name)
    body_path.write_text(body_markdown(surface=surface, changes=changes), encoding="utf-8")
    create_or_update_pull_request(
        surface=surface,
        body_path=body_path,
        base_branch=base_branch,
        repository=repository,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate separate update PRs for generated docs surfaces.")
    parser.add_argument(
        "--surface",
        action="append",
        choices=tuple(surface.key for surface in SURFACES),
        help="Limit execution to a surface. Repeat to include multiple surfaces. Defaults to all surfaces.",
    )
    parser.add_argument("--base-branch")
    parser.add_argument("--repository")
    args = parser.parse_args()
    args.base_branch = args.base_branch or base_branch_from_environment()
    args.repository = args.repository or repository_from_environment()
    return args


def selected_surfaces(surface_keys: Sequence[str] | None) -> tuple[UpdateSurface, ...]:
    if not surface_keys:
        return SURFACES
    requested = tuple(dict.fromkeys(surface_keys))
    return tuple(surface for surface in SURFACES if surface.key in requested)


def main() -> int:
    args = parse_args()
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    base_sha = git("rev-parse", "HEAD", capture=True)

    for surface in selected_surfaces(args.surface):
        process_surface(
            surface=surface,
            base_sha=base_sha,
            base_branch=args.base_branch,
            repository=args.repository,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
