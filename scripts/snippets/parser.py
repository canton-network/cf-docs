from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .model import (
    Diagnostic,
    IfVersionDirective,
    ParsedPage,
    SnippetDirective,
    SnippetValidationError,
    SourceKind,
    SourceReference,
    Span,
)


TAG_RE = re.compile(
    r"<(?P<closing>/)?(?P<name>Snippet|IfVersion|Else)\b(?P<body>(?:[^\"'>]|\"[^\"]*\"|'[^']*')*?)(?P<self_closing>/)?>",
    re.DOTALL,
)
ATTRIBUTE_RE = re.compile(
    r"\s+(?P<name>[A-Za-z][A-Za-z0-9]*)\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|\{(?P<number>[0-9]+)\})"
)
IMMUTABLE_RE = re.compile(
    r"https://github\.com/(?P<repo>[^/]+/[^/]+)/blob/(?P<commit>[0-9a-fA-F]{40})/(?P<path>.+)"
)
PULL_REQUEST_RE = re.compile(
    r"https://github\.com/(?P<repo>[^/]+/[^/]+)/pull/(?P<number>[1-9][0-9]*)"
)
REPOSITORY_RE = re.compile(r"https://github\.com/(?P<repo>[^/]+/[^/]+)/?")
LOCAL_RE = re.compile(r"local://(?P<repo>[^/]+/[^/]+)/(?P<path>.+)")

SNIPPET_ATTRIBUTES = {"source", "path", "startAfter", "endBefore", "language"}
CONDITION_ATTRIBUTES = {"repository", "containsPullRequest"}


def load_registry(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Cannot read snippet repository registry {path}: {error}"
        ) from error
    repositories = payload.get("repositories")
    if not isinstance(repositories, dict) or not repositories:
        raise ValueError(
            f"Snippet repository registry {path} must contain repositories"
        )
    return repositories


def _masked_source(text: str) -> str:
    """Mask fenced code and MDX comments while preserving offsets and newlines."""

    chars = list(text)
    ranges: list[tuple[int, int]] = []
    ranges.extend(
        (match.start(), match.end())
        for match in re.finditer(r"(?ms)^(```|~~~).*?^\1\s*$", text)
    )
    ranges.extend(
        (match.start(), match.end())
        for match in re.finditer(r"(?s)\{?/\*.*?\*/\}?", text)
    )
    for start, end in ranges:
        for index in range(start, end):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


def _span(text: str, start: int, end: int) -> Span:
    line_start = text.rfind("\n", 0, start) + 1
    return Span(
        start=start,
        end=end,
        line=text.count("\n", 0, start) + 1,
        column=start - line_start + 1,
    )


def _diagnostic(
    path: Path, span: Span, code: str, message: str, remediation: str | None = None
) -> Diagnostic:
    return Diagnostic(path, span.line, span.column, code, message, remediation)


def _attributes(body: str) -> tuple[dict[str, str | int], str | None]:
    attributes: dict[str, str | int] = {}
    position = 0
    for match in ATTRIBUTE_RE.finditer(body):
        if body[position : match.start()].strip():
            return {}, body[position : match.start()].strip()
        name = match.group("name")
        if name in attributes:
            return {}, f"duplicate attribute {name!r}"
        value: str | int
        if match.group("number") is not None:
            value = int(match.group("number"))
        else:
            value = (
                match.group("double")
                if match.group("double") is not None
                else match.group("single")
            )
        attributes[name] = value
        position = match.end()
    if body[position:].strip():
        return {}, body[position:].strip()
    return attributes, None


def _safe_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not value.startswith(("/", "\\"))
        and "\\" not in value
        and ".." not in path.parts
    )


def _source_reference(
    attributes: dict[str, str | int],
    *,
    path: Path,
    span: Span,
    repositories: dict[str, dict[str, Any]],
    allow_local: bool,
) -> tuple[SourceReference | None, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    source = attributes.get("source")
    explicit_path = attributes.get("path")
    if not isinstance(source, str):
        return None, [
            _diagnostic(
                path, span, "SNIP002", "Snippet requires a quoted source attribute"
            )
        ]
    if explicit_path is not None and not isinstance(explicit_path, str):
        diagnostics.append(
            _diagnostic(path, span, "SNIP003", "Snippet path must be quoted")
        )
        return None, diagnostics

    immutable = IMMUTABLE_RE.fullmatch(source)
    pull_request = PULL_REQUEST_RE.fullmatch(source)
    local = LOCAL_RE.fullmatch(source)
    if immutable:
        if explicit_path is not None:
            diagnostics.append(
                _diagnostic(
                    path,
                    span,
                    "SNIP004",
                    "Immutable blob source already contains its path",
                )
            )
        reference = SourceReference(
            kind=SourceKind.IMMUTABLE,
            repository=immutable.group("repo"),
            commit=immutable.group("commit").lower(),
            path=immutable.group("path"),
        )
    elif pull_request:
        if not explicit_path:
            diagnostics.append(
                _diagnostic(
                    path,
                    span,
                    "SNIP005",
                    "Pull-request source requires a quoted path attribute",
                )
            )
            return None, diagnostics
        reference = SourceReference(
            kind=SourceKind.PULL_REQUEST,
            repository=pull_request.group("repo"),
            pull_request=int(pull_request.group("number")),
            path=explicit_path,
        )
    elif local:
        reference = SourceReference(
            kind=SourceKind.LOCAL,
            repository=local.group("repo"),
            path=local.group("path"),
        )
        if explicit_path is not None:
            diagnostics.append(
                _diagnostic(
                    path, span, "SNIP006", "Local source already contains its path"
                )
            )
        if not allow_local:
            diagnostics.append(
                _diagnostic(
                    path,
                    span,
                    "SNIP007",
                    "Local snippet references are preview-only and cannot be committed",
                    "Run `npm run snippets:resolve-local -- --page <page.source.mdx>` before pushing.",
                )
            )
    else:
        diagnostics.append(
            _diagnostic(
                path,
                span,
                "SNIP008",
                "Unsupported snippet source",
                "Use a full GitHub blob URL with a 40-character commit, a GitHub pull-request URL plus path, or local://owner/repo/path for local preview.",
            )
        )
        return None, diagnostics

    if reference.repository not in repositories:
        diagnostics.append(
            _diagnostic(
                path,
                span,
                "SNIP009",
                f"Repository {reference.repository!r} is not allowlisted",
            )
        )
    if not _safe_path(reference.path):
        diagnostics.append(
            _diagnostic(path, span, "SNIP010", f"Unsafe source path {reference.path!r}")
        )
    return reference, diagnostics


def parse_page(
    text: str,
    *,
    path: Path,
    repositories: dict[str, dict[str, Any]],
    allow_local: bool = False,
) -> ParsedPage:
    snippets: list[SnippetDirective] = []
    conditions: list[IfVersionDirective] = []
    diagnostics: list[Diagnostic] = []
    stack: list[str] = []
    condition_context: list[tuple[str, int] | None] = []
    else_counts: list[int] = []
    masked = _masked_source(text)

    for match in TAG_RE.finditer(masked):
        name = match.group("name")
        closing = bool(match.group("closing"))
        self_closing = bool(match.group("self_closing"))
        span = _span(text, match.start(), match.end())
        body = match.group("body")

        if closing:
            if body.strip() or self_closing:
                diagnostics.append(
                    _diagnostic(path, span, "SNIP011", f"Malformed closing {name} tag")
                )
                continue
            if not stack or stack[-1] != name:
                expected = stack[-1] if stack else "nothing"
                diagnostics.append(
                    _diagnostic(
                        path,
                        span,
                        "SNIP012",
                        f"Unexpected </{name}>; expected closing tag for {expected}",
                    )
                )
            else:
                stack.pop()
                if name == "IfVersion":
                    if condition_context:
                        condition_context.pop()
                    if else_counts:
                        else_counts.pop()
            continue

        attributes, malformed = _attributes(body)
        if malformed:
            diagnostics.append(
                _diagnostic(
                    path,
                    span,
                    "SNIP013",
                    f"Malformed {name} attributes near {malformed!r}",
                )
            )
            continue

        if name == "Snippet":
            if not self_closing:
                diagnostics.append(
                    _diagnostic(path, span, "SNIP014", "Snippet must be self-closing")
                )
            unknown = sorted(set(attributes) - SNIPPET_ATTRIBUTES)
            if unknown:
                diagnostics.append(
                    _diagnostic(
                        path,
                        span,
                        "SNIP015",
                        f"Unknown Snippet attribute(s): {', '.join(unknown)}",
                    )
                )
            language = attributes.get("language")
            if (
                not isinstance(language, str)
                or not language
                or not re.fullmatch(r"[A-Za-z0-9_+.-]+", language)
            ):
                diagnostics.append(
                    _diagnostic(
                        path,
                        span,
                        "SNIP016",
                        "Snippet requires a safe quoted language attribute",
                    )
                )
            start_after = attributes.get("startAfter")
            end_before = attributes.get("endBefore")
            if (start_after is None) != (end_before is None):
                diagnostics.append(
                    _diagnostic(
                        path,
                        span,
                        "SNIP017",
                        "Marker extraction requires both startAfter and endBefore",
                    )
                )
            elif start_after is not None and (
                not isinstance(start_after, str)
                or not isinstance(end_before, str)
                or not start_after
                or not end_before
                or start_after == end_before
            ):
                diagnostics.append(
                    _diagnostic(
                        path,
                        span,
                        "SNIP018",
                        "Snippet markers must be distinct, non-empty quoted strings",
                    )
                )
            reference, source_diagnostics = _source_reference(
                attributes,
                path=path,
                span=span,
                repositories=repositories,
                allow_local=allow_local,
            )
            diagnostics.extend(source_diagnostics)
            if reference and reference.kind is SourceKind.PULL_REQUEST:
                if not condition_context:
                    diagnostics.append(
                        _diagnostic(
                            path,
                            span,
                            "SNIP027",
                            "Candidate pull-request snippet must be inside IfVersion",
                        )
                    )
                elif condition_context[-1] != (
                    reference.repository,
                    reference.pull_request,
                ):
                    enclosing = condition_context[-1]
                    expected = (
                        f"{enclosing[0]}#{enclosing[1]}"
                        if enclosing is not None
                        else "an invalid IfVersion"
                    )
                    diagnostics.append(
                        _diagnostic(
                            path,
                            span,
                            "SNIP028",
                            "Candidate snippet does not match its enclosing IfVersion "
                            f"({expected})",
                        )
                    )
            if reference and isinstance(language, str) and language:
                snippets.append(
                    SnippetDirective(
                        source=reference,
                        language=language,
                        start_after=start_after
                        if isinstance(start_after, str)
                        else None,
                        end_before=end_before if isinstance(end_before, str) else None,
                        span=span,
                    )
                )
        elif name == "IfVersion":
            if self_closing:
                diagnostics.append(
                    _diagnostic(
                        path, span, "SNIP019", "IfVersion cannot be self-closing"
                    )
                )
            unknown = sorted(set(attributes) - CONDITION_ATTRIBUTES)
            if unknown:
                diagnostics.append(
                    _diagnostic(
                        path,
                        span,
                        "SNIP020",
                        f"Unknown IfVersion attribute(s): {', '.join(unknown)}",
                    )
                )
            repository_url = attributes.get("repository")
            candidate = attributes.get("containsPullRequest")
            repository_match = (
                REPOSITORY_RE.fullmatch(repository_url)
                if isinstance(repository_url, str)
                else None
            )
            if not repository_match:
                diagnostics.append(
                    _diagnostic(
                        path,
                        span,
                        "SNIP021",
                        "IfVersion repository must be a complete GitHub repository URL",
                    )
                )
            elif repository_match.group("repo") not in repositories:
                diagnostics.append(
                    _diagnostic(
                        path,
                        span,
                        "SNIP022",
                        f"Repository {repository_match.group('repo')!r} is not allowlisted",
                    )
                )
            if not isinstance(candidate, int) or candidate < 1:
                diagnostics.append(
                    _diagnostic(
                        path,
                        span,
                        "SNIP023",
                        "IfVersion containsPullRequest must be a positive integer expression",
                    )
                )
            context: tuple[str, int] | None = None
            if repository_match and isinstance(candidate, int) and candidate > 0:
                repository = repository_match.group("repo")
                conditions.append(IfVersionDirective(repository, candidate, span))
                context = (repository, candidate)
            condition_context.append(context)
            stack.append(name)
            else_counts.append(0)
        else:
            if self_closing or attributes:
                diagnostics.append(
                    _diagnostic(
                        path,
                        span,
                        "SNIP024",
                        "Else does not accept attributes and cannot be self-closing",
                    )
                )
            if not stack or stack[-1] != "IfVersion":
                diagnostics.append(
                    _diagnostic(
                        path,
                        span,
                        "SNIP025",
                        "Else must be a direct child of IfVersion",
                    )
                )
            elif else_counts:
                else_counts[-1] += 1
                if else_counts[-1] > 1:
                    diagnostics.append(
                        _diagnostic(
                            path,
                            span,
                            "SNIP029",
                            "IfVersion can contain at most one Else branch",
                        )
                    )
            stack.append(name)

    for name in reversed(stack):
        diagnostics.append(
            Diagnostic(
                path, text.count("\n") + 1, 1, "SNIP026", f"Unclosed <{name}> tag"
            )
        )
    if diagnostics:
        raise SnippetValidationError(diagnostics)
    return ParsedPage(tuple(snippets), tuple(conditions))
