from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def current_repository() -> str:
    return gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner", capture=True)


def reset_to_base(*, base_sha: str, clean_paths: Sequence[str]) -> None:
    git("switch", "--detach", base_sha)
    git("reset", "--hard", base_sha)
    git("clean", "-fd", "--", *clean_paths)


def write_base_file(base_sha: str, relative_path: str) -> Path:
    before = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
    before_path = Path(before.name)
    before.write(git("show", f"{base_sha}:{relative_path}", capture=True))
    before.close()
    return before_path


def has_changes(paths: Sequence[str]) -> bool:
    output = git("status", "--porcelain", "--", *paths, capture=True)
    return bool(output)


def push_branch(branch: str) -> None:
    branch_ref = f"refs/heads/{branch}"
    remote_output = git("ls-remote", "--heads", "origin", branch, capture=True)
    remote_sha = remote_output.split()[0] if remote_output else ""
    if remote_sha:
        git(
            "push",
            f"--force-with-lease={branch_ref}:{remote_sha}",
            "origin",
            f"HEAD:{branch_ref}",
        )
    else:
        git("push", "origin", f"HEAD:{branch_ref}")


def open_pull_request_number(*, branch: str, base_branch: str, repository: str) -> str:
    return gh(
        "pr",
        "list",
        "--repo",
        repository,
        "--head",
        branch,
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


def close_stale_pull_request(
    *,
    title: str,
    branch: str,
    base_branch: str,
    repository: str,
) -> None:
    existing_pr_number = open_pull_request_number(
        branch=branch,
        base_branch=base_branch,
        repository=repository,
    )
    if not existing_pr_number:
        return
    gh(
        "pr",
        "close",
        existing_pr_number,
        "--repo",
        repository,
        "--delete-branch",
        "--comment",
        f"Closing because the latest generated-docs automation run found no changes for {title}.",
    )
    print(f"Closed stale PR #{existing_pr_number} for {title}")


def create_or_update_pull_request(
    *,
    title: str,
    branch: str,
    paths: Sequence[str],
    body_path: Path,
    base_branch: str,
    repository: str,
) -> None:
    if not has_changes(paths):
        print(f"No changes for {title}")
        close_stale_pull_request(
            title=title,
            branch=branch,
            base_branch=base_branch,
            repository=repository,
        )
        return

    git("status", "--short", "--", *paths)
    git("add", "--", *paths)
    git("diff", "--cached", "--stat")
    git("diff", "--cached", "--check")
    git("commit", "--signoff", "-m", title)
    push_branch(branch)

    existing_pr_number = open_pull_request_number(
        branch=branch,
        base_branch=base_branch,
        repository=repository,
    )
    if existing_pr_number:
        gh(
            "pr",
            "edit",
            existing_pr_number,
            "--repo",
            repository,
            "--title",
            title,
            "--body-file",
            str(body_path),
        )
        return

    gh(
        "pr",
        "create",
        "--base",
        base_branch,
        "--head",
        branch,
        "--repo",
        repository,
        "--title",
        title,
        "--body-file",
        str(body_path),
    )
