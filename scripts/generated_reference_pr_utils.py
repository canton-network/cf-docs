from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(
    command: Sequence[str],
    *,
    capture: bool = False,
    env: Mapping[str, str] | None = None,
) -> str:
    kwargs: dict[str, object] = {
        "cwd": REPO_ROOT,
        "check": True,
        "text": True,
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
    if env is not None:
        merged_env = os.environ.copy()
        merged_env.update(env)
        kwargs["env"] = merged_env
    completed = subprocess.run(list(command), **kwargs)
    return completed.stdout.strip() if capture else ""


def git(*args: str, capture: bool = False) -> str:
    return run(("git", *args), capture=capture)


def gh(*args: str, capture: bool = False) -> str:
    return run(("gh", *args), capture=capture)


def env_for_token(token: str) -> dict[str, str]:
    return {"GH_TOKEN": token, "GITHUB_TOKEN": token}


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


def mark_pull_request_ready(*, pr_number: str, repository: str) -> None:
    subprocess.run(
        [
            "gh",
            "pr",
            "ready",
            pr_number,
            "--repo",
            repository,
        ],
        cwd=REPO_ROOT,
        check=False,
    )


def dispatch_mintlify_validation(*, repository: str, branch: str) -> None:
    gh(
        "workflow",
        "run",
        "mintlify-validate.yml",
        "--repo",
        repository,
        "--ref",
        branch,
    )
    print(f"Dispatched Mintlify validation for {branch}")


def check_runs_for_sha(*, repository: str, head_sha: str) -> list[dict[str, object]]:
    payload = gh(
        "api",
        f"repos/{repository}/commits/{head_sha}/check-runs",
        capture=True,
    )
    data = json.loads(payload)
    check_runs = data.get("check_runs", [])
    if not isinstance(check_runs, list):
        raise RuntimeError("GitHub check-runs response did not contain a list")
    return [check_run for check_run in check_runs if isinstance(check_run, dict)]


def wait_for_check_success(
    *,
    repository: str,
    head_sha: str,
    check_name: str,
    timeout_seconds: int = 1800,
    poll_seconds: int = 15,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    failed_conclusions = {"action_required", "cancelled", "failure", "skipped", "timed_out"}

    while True:
        matching_runs = [
            check_run
            for check_run in check_runs_for_sha(repository=repository, head_sha=head_sha)
            if check_run.get("name") == check_name
        ]
        if any(check_run.get("conclusion") == "success" for check_run in matching_runs):
            print(f"Required check {check_name!r} succeeded for {head_sha}")
            return

        failed_runs = [
            check_run
            for check_run in matching_runs
            if check_run.get("conclusion") in failed_conclusions
        ]
        if failed_runs:
            conclusions = ", ".join(str(check_run.get("conclusion")) for check_run in failed_runs)
            raise RuntimeError(f"Required check {check_name!r} failed for {head_sha}: {conclusions}")

        if time.monotonic() >= deadline:
            states = ", ".join(
                f"{check_run.get('status')}/{check_run.get('conclusion')}" for check_run in matching_runs
            )
            raise TimeoutError(
                f"Timed out waiting for required check {check_name!r} on {head_sha}; latest states: {states or 'none'}"
            )

        print(f"Waiting for required check {check_name!r} on {head_sha}")
        time.sleep(poll_seconds)


def maybe_merge_generated_pr(
    *,
    pr_number: str,
    repository: str,
    base_branch: str,
    branch: str,
    head_sha: str,
    enabled: bool = True,
) -> None:
    if not enabled:
        print(f"Generated-docs auto-merge disabled for PR #{pr_number}; leaving PR open.")
        return

    if base_branch != "main":
        print(f"Skipping generated-docs auto-merge for PR #{pr_number}: base branch is {base_branch!r}.")
        return

    token = os.environ.get("GENERATED_DOCS_MERGER_TOKEN", "")
    if not token:
        print(f"Generated-docs merger app token not configured; leaving PR #{pr_number} open.")
        return

    token_env = env_for_token(token)
    run(
        (
            "python3",
            "scripts/validate_generated_pr_policy.py",
            pr_number,
            "--repository",
            repository,
            "--base-branch",
            base_branch,
            "--head-branch",
            branch,
            "--head-sha",
            head_sha,
        ),
        env=token_env,
    )
    dispatch_mintlify_validation(repository=repository, branch=branch)
    wait_for_check_success(
        repository=repository,
        head_sha=head_sha,
        check_name="mintlify validate",
    )
    run(
        (
            "gh",
            "pr",
            "merge",
            pr_number,
            "--repo",
            repository,
            "--admin",
            "--squash",
            "--delete-branch",
            "--match-head-commit",
            head_sha,
        ),
        env=token_env,
    )
    print(f"Merged generated-docs PR #{pr_number}")


def create_or_update_pull_request(
    *,
    title: str,
    branch: str,
    paths: Sequence[str],
    body_path: Path,
    base_branch: str,
    repository: str,
    auto_merge: bool = True,
) -> str | None:
    if not has_changes(paths):
        print(f"No changes for {title}")
        close_stale_pull_request(
            title=title,
            branch=branch,
            base_branch=base_branch,
            repository=repository,
        )
        return None

    git("status", "--short", "--", *paths)
    git("add", "--", *paths)
    git("diff", "--cached", "--stat")
    git("diff", "--cached", "--check")
    git("commit", "--signoff", "-m", title)
    head_sha = git("rev-parse", "HEAD", capture=True)
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
        mark_pull_request_ready(pr_number=existing_pr_number, repository=repository)
        maybe_merge_generated_pr(
            pr_number=existing_pr_number,
            repository=repository,
            base_branch=base_branch,
            branch=branch,
            head_sha=head_sha,
            enabled=auto_merge,
        )
        return existing_pr_number

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
    pr_number = open_pull_request_number(
        branch=branch,
        base_branch=base_branch,
        repository=repository,
    )
    if not pr_number:
        raise RuntimeError(f"Could not find generated PR for branch {branch}")
    maybe_merge_generated_pr(
        pr_number=pr_number,
        repository=repository,
        base_branch=base_branch,
        branch=branch,
        head_sha=head_sha,
        enabled=auto_merge,
    )
    return pr_number
