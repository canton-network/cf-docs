from __future__ import annotations

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
