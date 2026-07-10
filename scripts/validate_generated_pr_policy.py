#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import update_generated_reference_prs


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_AUTHOR = "app/github-actions"


@dataclass(frozen=True)
class PolicyInput:
    pr_number: str
    repository: str
    base_branch: str
    head_branch: str
    head_sha: str
    expected_author: str = EXPECTED_AUTHOR


def run_gh_json(args: Sequence[str]) -> dict[str, Any]:
    completed = subprocess.run(
        ("gh", *args),
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def run_gh_lines(args: Sequence[str]) -> list[str]:
    completed = subprocess.run(
        ("gh", *args),
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def target_paths_by_branch() -> dict[str, tuple[str, ...]]:
    return {target.branch: target.paths for target in update_generated_reference_prs.UPDATE_TARGETS}


def path_is_allowed(path: str, allowed_paths: Sequence[str]) -> bool:
    normalized = path.strip("/")
    for allowed_path in allowed_paths:
        normalized_allowed = allowed_path.strip("/")
        if normalized == normalized_allowed or normalized.startswith(f"{normalized_allowed}/"):
            return True
    return False


def validate_policy(
    *,
    policy_input: PolicyInput,
    pr_metadata: dict[str, Any],
    changed_files: Sequence[str],
    branch_paths: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    errors: list[str] = []
    branch_paths = branch_paths if branch_paths is not None else target_paths_by_branch()

    author = pr_metadata.get("author") or {}
    author_login = author.get("login", "")
    if author_login != policy_input.expected_author:
        errors.append(
            f"expected PR author {policy_input.expected_author!r}, found {author_login!r}"
        )

    if pr_metadata.get("state") != "OPEN":
        errors.append(f"expected PR state 'OPEN', found {pr_metadata.get('state')!r}")

    if pr_metadata.get("isDraft"):
        errors.append("expected PR to be ready for review, found draft PR")

    if pr_metadata.get("baseRefName") != policy_input.base_branch:
        errors.append(
            f"expected base branch {policy_input.base_branch!r}, found {pr_metadata.get('baseRefName')!r}"
        )

    if pr_metadata.get("headRefName") != policy_input.head_branch:
        errors.append(
            f"expected head branch {policy_input.head_branch!r}, found {pr_metadata.get('headRefName')!r}"
        )

    if pr_metadata.get("headRefOid") != policy_input.head_sha:
        errors.append(
            f"expected head SHA {policy_input.head_sha!r}, found {pr_metadata.get('headRefOid')!r}"
        )

    allowed_paths = branch_paths.get(policy_input.head_branch)
    if allowed_paths is None:
        errors.append(f"head branch {policy_input.head_branch!r} is not a configured generated-doc branch")
        allowed_paths = ()

    if not changed_files:
        errors.append("expected generated PR to contain at least one changed file")

    disallowed_files = [
        path for path in changed_files if not path_is_allowed(path, allowed_paths)
    ]
    if disallowed_files:
        joined = ", ".join(disallowed_files)
        errors.append(f"changed files outside configured generated paths: {joined}")

    return errors


def pr_metadata(*, pr_number: str, repository: str) -> dict[str, Any]:
    return run_gh_json(
        (
            "pr",
            "view",
            pr_number,
            "--repo",
            repository,
            "--json",
            "author,baseRefName,headRefName,headRefOid,isDraft,state",
        )
    )


def pr_changed_files(*, pr_number: str, repository: str) -> list[str]:
    return run_gh_lines(("pr", "diff", pr_number, "--repo", repository, "--name-only"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated-doc PR auto-merge policy.")
    parser.add_argument("pr_number", help="Pull request number to validate.")
    parser.add_argument("--repository", required=True, help="GitHub repository, for example canton-network/cf-docs.")
    parser.add_argument("--base-branch", required=True, help="Expected PR base branch.")
    parser.add_argument("--head-branch", required=True, help="Expected generated PR head branch.")
    parser.add_argument("--head-sha", required=True, help="Expected generated PR head SHA.")
    parser.add_argument(
        "--expected-author",
        default=EXPECTED_AUTHOR,
        help=f"Expected PR author login. Defaults to {EXPECTED_AUTHOR}.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy_input = PolicyInput(
        pr_number=args.pr_number,
        repository=args.repository,
        base_branch=args.base_branch,
        head_branch=args.head_branch,
        head_sha=args.head_sha,
        expected_author=args.expected_author,
    )
    errors = validate_policy(
        policy_input=policy_input,
        pr_metadata=pr_metadata(pr_number=args.pr_number, repository=args.repository),
        changed_files=pr_changed_files(pr_number=args.pr_number, repository=args.repository),
    )
    if errors:
        for error in errors:
            print(f"Generated PR policy violation: {error}", file=sys.stderr)
        return 1

    print(f"Generated PR #{args.pr_number} passed auto-merge policy validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
