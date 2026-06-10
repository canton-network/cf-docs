from __future__ import annotations

import importlib
from pathlib import Path


def load_docs_env():
    return importlib.import_module("scripts.docs_env")


def test_repo_direnv_command_runs_x2mdx_directly_inside_nix_shell(monkeypatch) -> None:
    docs_env = load_docs_env()
    monkeypatch.delenv(docs_env.DIRENV_ENV_MARKER, raising=False)
    monkeypatch.setenv("IN_NIX_SHELL", "pure")

    assert docs_env.repo_direnv_command(Path("/repo"), "x2mdx", "openrpc") == [
        "python3",
        "-m",
        "x2mdx.cli",
        "openrpc",
    ]


def test_repo_direnv_command_uses_direnv_outside_nix_shell(monkeypatch) -> None:
    docs_env = load_docs_env()
    monkeypatch.delenv(docs_env.DIRENV_ENV_MARKER, raising=False)
    monkeypatch.delenv("IN_NIX_SHELL", raising=False)
    monkeypatch.setattr(docs_env.shutil, "which", lambda name: "/bin/direnv" if name == "direnv" else None)

    assert docs_env.repo_direnv_command(Path("/repo"), "python3", "script.py") == [
        "direnv",
        "exec",
        "/repo",
        "python3",
        "script.py",
    ]
