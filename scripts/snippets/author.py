from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .model import SnippetValidationError, SourceKind
from .parser import LOCAL_RE, PULL_REQUEST_RE, _masked_source, load_registry, parse_page
from .source import (
    GitHubClient,
    SourceResolutionError,
    SourceResolver,
    extract_snippet,
    repository_from_remote,
)

CF_DOCS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = CF_DOCS_ROOT / "config" / "snippet-repositories.json"
LOCAL_SOURCE_ATTRIBUTE_RE = re.compile(
    r"source=(?P<quote>[\"'])local://(?P<repo>[^/\"']+/[^/\"']+)/(?P<path>[^\"']+)(?P=quote)"
)
LANGUAGES = {
    ".daml": "daml",
    ".json": "json",
    ".md": "markdown",
    ".mdx": "mdx",
    ".py": "python",
    ".rst": "rst",
    ".scala": "scala",
    ".sh": "bash",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".yaml": "yaml",
    ".yml": "yaml",
}


def infer_language(path: str) -> str:
    language = LANGUAGES.get(Path(path).suffix.lower())
    if not language:
        raise ValueError(
            f"Cannot infer a language from {path!r}; pass --language explicitly"
        )
    return language


def repository_for_checkout(checkout: Path) -> str:
    root = checkout.expanduser().resolve()
    try:
        remote = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f"Local source is not a git checkout: {root}") from error
    repository = repository_from_remote(remote)
    if not repository:
        raise ValueError(
            f"Local checkout origin is not a supported GitHub URL: {remote}"
        )
    return repository


def snippet_declaration(
    *,
    source: str,
    path: str | None,
    language: str,
    start_after: str | None,
    end_before: str | None,
) -> str:
    lines = ["<Snippet", f'  source="{source}"']
    if path:
        lines.append(f'  path="{path}"')
    if start_after:
        lines.append(f'  startAfter="{start_after}"')
        lines.append(f'  endBefore="{end_before}"')
    lines.extend((f'  language="{language}"', "/>"))
    return "\n".join(lines)


def _parse_declaration(
    declaration: str,
    *,
    repositories: dict[str, dict[str, Any]],
    allow_local: bool,
):
    pull_request = PULL_REQUEST_RE.search(declaration)
    if pull_request:
        repository = pull_request.group("repo")
        number = pull_request.group("number")
        declaration = (
            f'<IfVersion repository="https://github.com/{repository}" '
            f"containsPullRequest={{{number}}}>\n"
            f"{declaration}\n<Else>\n</Else>\n</IfVersion>"
        )
    page = parse_page(
        declaration,
        path=Path("<generated declaration>"),
        repositories=repositories,
        allow_local=allow_local,
    )
    return page.snippets[0]


def _markers(args: argparse.Namespace) -> tuple[str | None, str | None]:
    if args.marker:
        return f"{args.marker}_START", f"{args.marker}_END"
    if bool(args.start_after) != bool(args.end_before):
        raise ValueError("Pass both --start-after and --end-before")
    return args.start_after, args.end_before


def add(args: argparse.Namespace, repositories: dict[str, dict[str, Any]]) -> int:
    start_after, end_before = _markers(args)
    local_checkouts: dict[str, Path] = {}
    if args.local_checkout:
        repository = repository_for_checkout(args.local_checkout)
        if repository not in repositories:
            raise ValueError(f"Repository {repository!r} is not allowlisted")
        if args.source.startswith(("http://", "https://", "local://")):
            raise ValueError(
                "With --local-checkout, --source must be a repository-relative path"
            )
        source = f"local://{repository}/{args.source}"
        path = None
        local_checkouts[repository] = args.local_checkout
    else:
        source = args.source
        path = args.path
    source_path = path
    if source_path is None:
        immutable_path = re.search(r"/blob/[0-9a-fA-F]{40}/(?P<path>.+)$", source)
        local_path = LOCAL_RE.fullmatch(source)
        source_path = (
            immutable_path.group("path")
            if immutable_path
            else local_path.group("path")
            if local_path
            else None
        )
    language = args.language or (infer_language(source_path) if source_path else None)
    if not language:
        raise ValueError("Pass --language when the source path has no known extension")
    declaration = snippet_declaration(
        source=source,
        path=path,
        language=language,
        start_after=start_after,
        end_before=end_before,
    )
    directive = _parse_declaration(
        declaration,
        repositories=repositories,
        allow_local=bool(args.local_checkout),
    )
    if not args.skip_source_check:
        resolver = SourceResolver(
            GitHubClient(),
            repositories=set(repositories),
            local_checkouts=local_checkouts,
            allow_local=bool(args.local_checkout),
        )
        resolved = resolver.resolve(directive.source)
        extract_snippet(directive, resolved)
    print(declaration)
    if directive.source.kind is SourceKind.LOCAL:
        print(
            "\nPreview-only local ref. Before pushing, run "
            "`npm run snippets:resolve-local -- --page <page.source.mdx> --pull-request <number>`.",
            file=sys.stderr,
        )
    return 0


def resolve_local(
    args: argparse.Namespace, repositories: dict[str, dict[str, Any]]
) -> int:
    page = args.page.expanduser().resolve()
    original = page.read_text(encoding="utf-8")
    masked = _masked_source(original)
    matches = list(LOCAL_SOURCE_ATTRIBUTE_RE.finditer(masked))
    if args.repository:
        matches = [match for match in matches if match.group("repo") == args.repository]
    repositories_found = {match.group("repo") for match in matches}
    if not matches:
        raise ValueError(f"No matching local:// snippet references found in {page}")
    if len(repositories_found) != 1:
        rendered = ", ".join(sorted(repositories_found))
        raise ValueError(
            f"Found local refs for multiple repositories ({rendered}); pass --repository"
        )
    repository = next(iter(repositories_found))
    if repository not in repositories:
        raise ValueError(f"Repository {repository!r} is not allowlisted")

    rewritten = original
    for match in reversed(matches):
        quote = match.group("quote")
        path = match.group("path")
        replacement = (
            f"source={quote}https://github.com/{repository}/pull/{args.pull_request}{quote} "
            f"path={quote}{path}{quote}"
        )
        rewritten = rewritten[: match.start()] + replacement + rewritten[match.end() :]
    parsed = parse_page(
        rewritten,
        path=page,
        repositories=repositories,
        allow_local=False,
    )
    resolved_candidates = [
        directive
        for directive in parsed.snippets
        if directive.source.repository == repository
        and directive.source.pull_request == args.pull_request
    ]
    if len(resolved_candidates) < len(matches):
        raise ValueError(
            "Not every local reference resolved to the requested candidate PR"
        )
    if not args.skip_source_check:
        resolver = SourceResolver(GitHubClient(), repositories=set(repositories))
        for directive in resolved_candidates:
            extract_snippet(directive, resolver.resolve(directive.source))
    page.write_text(rewritten, encoding="utf-8")
    print(
        f"Resolved {len(matches)} local reference(s) in {page} to {repository}#{args.pull_request}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scaffold inline snippet declarations")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Validate and print a declaration")
    add_parser.add_argument("--source", required=True)
    add_parser.add_argument("--path")
    add_parser.add_argument("--local-checkout", type=Path)
    add_parser.add_argument("--language")
    marker_group = add_parser.add_mutually_exclusive_group()
    marker_group.add_argument("--marker")
    marker_group.add_argument("--start-after")
    add_parser.add_argument("--end-before")
    add_parser.add_argument("--skip-source-check", action="store_true")

    resolve = subparsers.add_parser(
        "resolve-local", help="Replace preview-only local refs with a candidate PR ref"
    )
    resolve.add_argument("--page", type=Path, required=True)
    resolve.add_argument("--pull-request", type=int, required=True)
    resolve.add_argument("--repository")
    resolve.add_argument("--skip-source-check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repositories = load_registry(args.registry)
        if args.command == "add":
            return add(args, repositories)
        return resolve_local(args, repositories)
    except (
        OSError,
        SnippetValidationError,
        SourceResolutionError,
        ValueError,
    ) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
