from __future__ import annotations

import subprocess

from scripts import generated_reference_pr_utils as pr_utils


def test_current_repository_uses_actions_environment_without_github_api(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "canton-network/cf-docs")
    monkeypatch.setattr(
        pr_utils,
        "gh",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("GitHub API should not be queried")
        ),
    )

    assert pr_utils.current_repository() == "canton-network/cf-docs"


def test_current_repository_falls_back_to_github_cli(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(pr_utils, "gh", lambda *_args, **_kwargs: "canton-network/cf-docs")

    assert pr_utils.current_repository() == "canton-network/cf-docs"


def test_push_branch_retries_failed_pushes(monkeypatch) -> None:
    push_calls: list[tuple[str, ...]] = []
    sleeps: list[float] = []

    def fake_git(*args: str, capture: bool = False) -> str:
        if args[:3] == ("ls-remote", "--heads", "origin"):
            return ""
        push_calls.append(args)
        if len(push_calls) < 3:
            raise subprocess.CalledProcessError(1, ("git", *args))
        return ""

    monkeypatch.setattr(pr_utils, "git", fake_git)
    monkeypatch.setattr(pr_utils.time, "sleep", sleeps.append)

    pr_utils.push_branch("generated-references/example/update")

    assert push_calls == [
        (
            "push",
            "origin",
            "HEAD:refs/heads/generated-references/example/update",
        )
    ] * 3
    assert sleeps == [5.0, 10.0]


def test_generated_pr_merge_retries_only_merge_command(monkeypatch) -> None:
    events: list[tuple[str, ...]] = []
    sleeps: list[float] = []
    merge_attempts = 0

    def fake_run(command, **_kwargs):
        nonlocal merge_attempts
        command_tuple = tuple(command)
        events.append(command_tuple)
        if command_tuple[:3] == ("gh", "pr", "merge"):
            merge_attempts += 1
            if merge_attempts < 3:
                raise subprocess.CalledProcessError(1, command_tuple)
        return ""

    monkeypatch.setenv("GENERATED_DOCS_MERGER_TOKEN", "token")
    monkeypatch.setattr(pr_utils, "run", fake_run)
    monkeypatch.setattr(pr_utils.time, "sleep", sleeps.append)
    monkeypatch.setattr(pr_utils, "dispatch_mintlify_validation", lambda **_kwargs: None)
    monkeypatch.setattr(pr_utils, "wait_for_check_success", lambda **_kwargs: None)

    pr_utils.maybe_merge_generated_pr(
        pr_number="1383",
        repository="canton-network/cf-docs",
        base_branch="main",
        branch="generated-references/example/update",
        head_sha="abc123",
    )

    validation_commands = [command for command in events if command[0] == "python3"]
    merge_commands = [command for command in events if command[:3] == ("gh", "pr", "merge")]
    assert len(validation_commands) == 1
    assert len(merge_commands) == 3
    assert sleeps == [5.0, 10.0]


def test_publish_retry_stops_after_three_failures(monkeypatch) -> None:
    attempts = 0
    sleeps: list[float] = []

    def fail() -> str:
        nonlocal attempts
        attempts += 1
        raise subprocess.CalledProcessError(1, ("git", "push"))

    monkeypatch.setattr(pr_utils.time, "sleep", sleeps.append)

    try:
        pr_utils.retry_publish("Generated branch push", fail)
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("Expected final publication failure to be raised")

    assert attempts == 3
    assert sleeps == [5.0, 10.0]
