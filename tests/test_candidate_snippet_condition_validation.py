from __future__ import annotations

from scripts.snippets.model import (
    CandidateConditionRule,
    IfVersionCondition,
    ImmutableSourceReference,
    PullRequestSnippetSource,
    SnippetConditionContext,
    SnippetTag,
    Span,
)
from scripts.snippets.semantics import validate_candidate_condition

SPAN = Span(start=0, end=1, line=1, column=1)
SNIPPET = SnippetTag(attributes=(), span=SPAN)
CONDITION = IfVersionCondition(
    repository="canton-network/splice",
    contains_pull_request=6123,
    span=SPAN,
)
CANDIDATE = PullRequestSnippetSource(
    repository="canton-network/splice",
    pull_request=6123,
    path="apps/file.yaml",
)


def test_accepts_candidate_matching_enclosing_condition() -> None:
    context = SnippetConditionContext(snippet=SNIPPET, condition=CONDITION)

    assert validate_candidate_condition(CANDIDATE, context) == ()


def test_requires_condition_around_candidate() -> None:
    context = SnippetConditionContext(snippet=SNIPPET, condition=None)

    issues = validate_candidate_condition(CANDIDATE, context)
    assert {issue.rule for issue in issues} == {
        CandidateConditionRule.CONDITION_REQUIRED
    }


def test_requires_repository_and_pr_identity_match() -> None:
    context = SnippetConditionContext(snippet=SNIPPET, condition=CONDITION)
    other_candidate = PullRequestSnippetSource(
        repository="canton-network/splice",
        pull_request=6124,
        path="apps/file.yaml",
    )

    issues = validate_candidate_condition(other_candidate, context)
    assert {issue.rule for issue in issues} == {
        CandidateConditionRule.IDENTITY_MISMATCH
    }


def test_does_not_restrict_non_candidate_sources() -> None:
    immutable = ImmutableSourceReference(
        repository="canton-network/splice",
        commit="2c941ea9e834d7602d388f3271c0f864025ea756",
        path="apps/file.yaml",
    )
    context = SnippetConditionContext(snippet=SNIPPET, condition=None)

    assert validate_candidate_condition(immutable, context) == ()
