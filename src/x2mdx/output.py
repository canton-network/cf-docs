"""Shared output-side data structures for generated MDX pages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias, Union


FrontmatterValue: TypeAlias = str | bool | int | float | list[str]


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class BulletList:
    items: list[str]


@dataclass(frozen=True)
class Table:
    headers: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class RawMarkdown:
    text: str


Block = Union[Heading, Paragraph, BulletList, Table, RawMarkdown]


@dataclass(frozen=True)
class Page:
    path: str
    title: str
    description: str | None = None
    frontmatter: dict[str, FrontmatterValue] = field(default_factory=dict)
    blocks: list[Block] = field(default_factory=list)
