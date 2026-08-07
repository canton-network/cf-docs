from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class SourceKind(str, Enum):
    IMMUTABLE = "immutable"
    PULL_REQUEST = "pull_request"
    LOCAL = "local"


@dataclass(frozen=True)
class SourceReference:
    kind: SourceKind
    repository: str
    path: str
    commit: str | None = None
    pull_request: int | None = None


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    line: int
    column: int


@dataclass(frozen=True)
class SnippetDirective:
    source: SourceReference
    language: str
    start_after: str | None
    end_before: str | None
    line_start: int | None
    line_end: int | None
    normalization: str | None
    trim: bool
    strip_trailing_whitespace: bool
    replace_from: str | None
    replace_with: str | None
    span: Span


@dataclass(frozen=True)
class IfVersionDirective:
    repository: str
    contains_pull_request: int
    span: Span


@dataclass(frozen=True)
class ParsedPage:
    snippets: tuple[SnippetDirective, ...]
    conditions: tuple[IfVersionDirective, ...]


@dataclass(frozen=True)
class Diagnostic:
    path: Path
    line: int
    column: int
    code: str
    message: str
    remediation: str | None = None

    def format(self) -> str:
        rendered = f"{self.path}:{self.line}:{self.column}: {self.code}: {self.message}"
        if self.remediation:
            rendered += f"\n  remediation: {self.remediation}"
        return rendered


class SnippetValidationError(Exception):
    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics = diagnostics
        super().__init__("\n".join(diagnostic.format() for diagnostic in diagnostics))
