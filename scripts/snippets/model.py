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
