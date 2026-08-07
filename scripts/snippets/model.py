from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    line: int
    column: int


@dataclass(frozen=True)
class DirectiveAttribute:
    name: str
    value: str | int


@dataclass(frozen=True)
class SnippetTag:
    attributes: tuple[DirectiveAttribute, ...]
    span: Span

    def attribute(self, name: str) -> str | int | None:
        return next(
            (attribute.value for attribute in self.attributes if attribute.name == name),
            None,
        )


@dataclass(frozen=True)
class IfVersionTag:
    attributes: tuple[DirectiveAttribute, ...]
    span: Span
    closing: bool

    def attribute(self, name: str) -> str | int | None:
        return next(
            (attribute.value for attribute in self.attributes if attribute.name == name),
            None,
        )


@dataclass(frozen=True)
class ElseTag:
    span: Span
    closing: bool


@dataclass(frozen=True)
class ImmutableSourceReference:
    repository: str
    commit: str
    path: str


@dataclass(frozen=True)
class PullRequestSourceReference:
    repository: str
    pull_request: int


@dataclass(frozen=True)
class LocalSourceReference:
    repository: str
    path: str
