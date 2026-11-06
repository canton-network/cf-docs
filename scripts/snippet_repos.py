"""Snippet source repositories, discovered from their remote manifests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


CF_DOCS_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SUFFIX = "-snippet-list-remote.json"


@dataclass(frozen=True)
class SnippetRepo:
    name: str
    config_name: str
    aliases: tuple[str, ...]
    output_repo_name: str | None = None
    prepare: tuple[str, ...] = ()


# Commands that must run in a source checkout before its snippet sources exist.
REPO_PREPARATION: dict[str, tuple[str, ...]] = {
    "canton": ('sbt "docs-open / reset" "docs-open / generateSphinxSnippets"',),
}


def discover_repos(config_dir: Path) -> dict[str, SnippetRepo]:
    """Return one snippet repository per ``<name>-snippet-list-remote.json`` manifest."""
    repos: dict[str, SnippetRepo] = {}
    for path in sorted(config_dir.glob(f"*{MANIFEST_SUFFIX}")):
        name = path.name.removesuffix(MANIFEST_SUFFIX)
        repos[name] = SnippetRepo(
            name=name,
            config_name=path.name,
            aliases=(name,),
            prepare=REPO_PREPARATION.get(name, ()),
        )
    return repos


REPOS: dict[str, SnippetRepo] = discover_repos(CF_DOCS_ROOT / "config" / "snippet-config")


def source_env_names(repo: SnippetRepo) -> list[str]:
    names = {repo.name, *repo.aliases}
    env_names: list[str] = []
    for name in sorted(names):
        token = "".join(ch if ch.isalnum() else "_" for ch in name).upper()
        env_names.extend((f"SNIPPET_REPO_DIR_{token}", f"{token}_REPO_DIR"))
    return env_names


def candidate_roots() -> list[Path]:
    roots: list[Path] = []
    current = CF_DOCS_ROOT
    for parent in (current.parent, current.parent.parent, current.parent.parent.parent):
        if parent and parent not in roots:
            roots.append(parent)
        worktrees = parent / ".worktrees"
        if worktrees.is_dir() and worktrees not in roots:
            roots.append(worktrees)
    extra = os.environ.get("SNIPPET_REPOS_ROOT")
    if extra:
        roots.insert(0, Path(extra).expanduser())
    return roots


def is_repo_dir(path: Path) -> bool:
    return (path / ".git").exists()


def find_source_dir(repo: SnippetRepo, explicit: Path | None) -> Path:
    if explicit:
        path = explicit.expanduser().resolve()
        if not is_repo_dir(path):
            raise SystemExit(f"Source directory is not a git checkout: {path}")
        return path

    for env_name in source_env_names(repo):
        value = os.environ.get(env_name)
        if value:
            path = Path(value).expanduser().resolve()
            if not is_repo_dir(path):
                raise SystemExit(f"{env_name} is not a git checkout: {path}")
            return path

    exact: list[Path] = []
    prefix: list[Path] = []
    for root in candidate_roots():
        for alias in repo.aliases:
            candidate = root / alias
            if is_repo_dir(candidate):
                exact.append(candidate.resolve())
        if root.is_dir():
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                if any(child.name.startswith(f"{alias}-") for alias in repo.aliases):
                    if is_repo_dir(child):
                        prefix.append(child.resolve())

    matches = sorted(dict.fromkeys(exact + prefix))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        env_hint = source_env_names(repo)[0]
        raise SystemExit(
            f"Could not find a local checkout for {repo.name}. "
            f"Pass --source-dir or set {env_hint}."
        )
    formatted = "\n  ".join(str(path) for path in matches)
    raise SystemExit(
        f"Found multiple possible checkouts for {repo.name}; pass --source-dir:\n  {formatted}"
    )
