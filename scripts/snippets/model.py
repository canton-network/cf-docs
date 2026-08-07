from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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


class ConditionStructureRule(str, Enum):
    UNEXPECTED_CLOSE = "unexpected_close"
    ELSE_NOT_DIRECT_CHILD = "else_not_direct_child"
    MULTIPLE_ELSE = "multiple_else"
    ELSE_NOT_FINAL = "else_not_final"
    UNCLOSED_TAG = "unclosed_tag"


@dataclass(frozen=True)
class ConditionStructureIssue:
    rule: ConditionStructureRule
    span: Span
    message: str


@dataclass(frozen=True)
class IfVersionCondition:
    repository: str
    contains_pull_request: int
    span: Span


class IfVersionAttributeRule(str, Enum):
    UNKNOWN_ATTRIBUTE = "unknown_attribute"
    INVALID_REPOSITORY = "invalid_repository"
    UNREGISTERED_REPOSITORY = "unregistered_repository"
    INVALID_PULL_REQUEST = "invalid_pull_request"


@dataclass(frozen=True)
class IfVersionAttributeIssue:
    rule: IfVersionAttributeRule
    span: Span
    message: str


@dataclass(frozen=True)
class IfVersionAttributeValidation:
    condition: IfVersionCondition | None
    issues: tuple[IfVersionAttributeIssue, ...]
