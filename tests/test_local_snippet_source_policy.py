from __future__ import annotations

from scripts.snippets.model import (
    ImmutableSourceReference,
    LocalSourceReference,
    Span,
)
from scripts.snippets.validation import validate_local_source_policy

SPAN = Span(start=0, end=1, line=1, column=1)
LOCAL = LocalSourceReference(
    repository="canton-network/splice", path="apps/file.yaml"
)
IMMUTABLE = ImmutableSourceReference(
    repository="canton-network/splice",
    commit="2c941ea9e834d7602d388f3271c0f864025ea756",
    path="apps/file.yaml",
)


def test_rejects_local_reference_in_committed_page_mode() -> None:
    issues = validate_local_source_policy(
        LOCAL, span=SPAN, allow_local=False
    )

    assert len(issues) == 1
    assert "preview-only" in issues[0].message


def test_accepts_local_reference_in_explicit_preview_mode() -> None:
    assert validate_local_source_policy(
        LOCAL, span=SPAN, allow_local=True
    ) == ()


def test_policy_does_not_restrict_nonlocal_references() -> None:
    assert validate_local_source_policy(
        IMMUTABLE, span=SPAN, allow_local=False
    ) == ()
