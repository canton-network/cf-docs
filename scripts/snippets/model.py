from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


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


@dataclass(frozen=True)
class PullRequestSnippetSource:
    repository: str
    pull_request: int
    path: str


class SnippetSourceAttributeRule(str, Enum):
    SOURCE_REQUIRED = "source_required"
    UNSUPPORTED_SOURCE = "unsupported_source"
    PATH_MUST_BE_QUOTED = "path_must_be_quoted"
    IMMUTABLE_PATH_FORBIDDEN = "immutable_path_forbidden"
    PULL_REQUEST_PATH_REQUIRED = "pull_request_path_required"
    LOCAL_PATH_FORBIDDEN = "local_path_forbidden"


@dataclass(frozen=True)
class SnippetSourceAttributeIssue:
    rule: SnippetSourceAttributeRule
    span: Span
    message: str


@dataclass(frozen=True)
class SnippetSourceAttributeValidation:
    source: (
        ImmutableSourceReference
        | PullRequestSnippetSource
        | LocalSourceReference
        | None
    )
    issues: tuple[SnippetSourceAttributeIssue, ...]


class SnippetSourceSafetyRule(str, Enum):
    UNREGISTERED_REPOSITORY = "unregistered_repository"
    UNSAFE_PATH = "unsafe_path"


@dataclass(frozen=True)
class SnippetSourceSafetyIssue:
    rule: SnippetSourceSafetyRule
    span: Span
    message: str


@dataclass(frozen=True)
class LocalSourcePolicyIssue:
    span: Span
    message: str


class SnippetAttributeRule(str, Enum):
    UNKNOWN_ATTRIBUTE = "unknown_attribute"
    INVALID_LANGUAGE = "invalid_language"
    INVALID_MARKERS = "invalid_markers"


@dataclass(frozen=True)
class SnippetAttributeIssue:
    rule: SnippetAttributeRule
    span: Span
    message: str


@dataclass(frozen=True)
class SnippetConditionContext:
    snippet: SnippetTag
    condition: IfVersionCondition | None


class CandidateConditionRule(str, Enum):
    CONDITION_REQUIRED = "condition_required"
    IDENTITY_MISMATCH = "identity_mismatch"


@dataclass(frozen=True)
class CandidateConditionIssue:
    rule: CandidateConditionRule
    span: Span
    message: str


@dataclass(frozen=True)
class Diagnostic:
    path: Path
    span: Span
    code: str
    message: str
    remediation: str | None = None

    def format(self) -> str:
        rendered = (
            f"{self.path}:{self.span.line}:{self.span.column}: "
            f"{self.code}: {self.message}"
        )
        if self.remediation is not None:
            rendered += f"\n  remediation: {self.remediation}"
        return rendered


class DirectiveSyntaxRule(str, Enum):
    MALFORMED_ATTRIBUTES = "malformed_attributes"
    DUPLICATE_ATTRIBUTE = "duplicate_attribute"
    SNIPPET_NOT_SELF_CLOSING = "snippet_not_self_closing"
    IF_VERSION_SELF_CLOSING = "if_version_self_closing"
    ELSE_SELF_CLOSING = "else_self_closing"
    CLOSING_ATTRIBUTES = "closing_attributes"
    ELSE_ATTRIBUTES = "else_attributes"


@dataclass(frozen=True)
class ConditionPageValidation:
    tags: tuple[IfVersionTag | ElseTag, ...]
    conditions: tuple[IfVersionCondition, ...]
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class ValidatedSnippet:
    tag: SnippetTag
    source: (
        ImmutableSourceReference
        | PullRequestSnippetSource
        | LocalSourceReference
    )
    condition: IfVersionCondition | None


@dataclass(frozen=True)
class SnippetPageValidation:
    snippets: tuple[ValidatedSnippet, ...]
    diagnostics: tuple[Diagnostic, ...]
