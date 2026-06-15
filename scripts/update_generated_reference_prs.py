#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import generated_reference_pr_utils as pr_utils
import summarize_version_changes


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class UpdateTarget:
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


UPDATE_TARGETS = (
    UpdateTarget(
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
)


def generated_clean_paths() -> tuple[str, ...]:
    paths = {".internal"}
    for target in UPDATE_TARGETS:
        paths.update(target.paths)
    return tuple(sorted(paths))


def current_base_branch() -> str:
    branch = pr_utils.git("branch", "--show-current", capture=True)
    if branch:
        return branch
    ref_name = os.environ.get("GITHUB_REF_NAME")
    if ref_name:
        return ref_name
    raise RuntimeError("Could not determine base branch; pass --base-branch")


def body_markdown(*, target: UpdateTarget, changes: list[str]) -> str:
    change_text = "\n".join(changes) if changes else "- No version values changed."
    validation = "\n".join(f"- `{command}`" for command in target.validation)
    return (
        f"{target.description}\n\n"
        f"Version changes:\n"
        f"{change_text}\n\n"
        f"Validation run by the workflow:\n"
        f"{validation}\n"
    )


def summarize_target_changes(target: UpdateTarget, before_path: Path) -> list[str]:
    after_path = REPO_ROOT / target.summary_path
    if target.summary_kind == "dashboard":
        return summarize_version_changes.dashboard_changes(before_path, after_path)
    if target.summary_kind == "source-config":
        if target.summary_label is None:
            raise ValueError(f"Update target {target.key} must define summary_label")
        return summarize_version_changes.source_config_changes(
            before_path,
            after_path,
            label=target.summary_label,
        )
    raise ValueError(f"Unknown summary kind for {target.key}: {target.summary_kind}")


def reset_to_base(base_sha: str) -> None:
    pr_utils.reset_to_base(base_sha=base_sha, clean_paths=generated_clean_paths())


def create_or_update_pull_request(
    *,
    target: UpdateTarget,
    body_path: Path,
    base_branch: str,
    repository: str,
) -> None:
    pr_utils.create_or_update_pull_request(
        title=target.title,
        branch=target.branch,
        paths=target.paths,
        body_path=body_path,
        base_branch=base_branch,
        repository=repository,
    )


def process_target(*, target: UpdateTarget, base_sha: str, base_branch: str, repository: str) -> None:
    reset_to_base(base_sha)
    before_path = pr_utils.write_base_file(base_sha, target.summary_path)

    for command in target.generate_commands:
        pr_utils.run(command)

    changes = summarize_target_changes(target, before_path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as body_file:
        body_path = Path(body_file.name)
    body_path.write_text(body_markdown(target=target, changes=changes), encoding="utf-8")
    create_or_update_pull_request(
        target=target,
        body_path=body_path,
        base_branch=base_branch,
        repository=repository,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate separate update PRs for configured update targets.")
    target_keys = tuple(target.key for target in UPDATE_TARGETS)
    parser.add_argument(
        "--targets",
        nargs="+",
        required=True,
        metavar="TARGET",
        choices=("all", *target_keys),
        help=f"Targets to run. Use 'all' by itself, or list one or more of: {', '.join(target_keys)}.",
    )
    parser.add_argument(
        "--base-branch",
        help="Base branch for generated PRs. Defaults to the current checkout branch.",
    )
    parser.add_argument(
        "--repository",
        help="GitHub repository for generated PRs. Defaults to the current gh repository.",
    )
    args = parser.parse_args()
    if "all" in args.targets and len(args.targets) > 1:
        parser.error("pass --targets all by itself, or list specific target keys")
    args.base_branch = args.base_branch or current_base_branch()
    args.repository = args.repository or pr_utils.current_repository()
    return args


def targets_to_run(target_keys: Sequence[str]) -> tuple[UpdateTarget, ...]:
    if not target_keys:
        raise ValueError("No update targets selected")
    if len(target_keys) == 1 and target_keys[0] == "all":
        return UPDATE_TARGETS
    if "all" in target_keys:
        raise ValueError("'all' cannot be combined with specific update targets")
    requested = tuple(dict.fromkeys(target_keys))
    return tuple(target for target in UPDATE_TARGETS if target.key in requested)


def main() -> int:
    args = parse_args()
    pr_utils.git("config", "user.name", "github-actions[bot]")
    pr_utils.git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    base_sha = pr_utils.git("rev-parse", "HEAD", capture=True)

    for target in targets_to_run(args.targets):
        process_target(
            target=target,
            base_sha=base_sha,
            base_branch=args.base_branch,
            repository=args.repository,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
