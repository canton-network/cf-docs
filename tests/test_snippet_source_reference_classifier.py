from __future__ import annotations

from scripts.snippets.model import (
    ImmutableSourceReference,
    LocalSourceReference,
    PullRequestSourceReference,
)
from scripts.snippets.references import parse_source_reference

COMMIT = "2c941ea9e834d7602d388f3271c0f864025ea756"


def test_classifies_each_supported_source_form() -> None:
    assert isinstance(
        parse_source_reference(
            f"https://github.com/canton-network/splice/blob/{COMMIT}/file.yaml"
        ),
        ImmutableSourceReference,
    )
    assert isinstance(
        parse_source_reference(
            "https://github.com/canton-network/splice/pull/6123"
        ),
        PullRequestSourceReference,
    )
    assert isinstance(
        parse_source_reference("local://canton-network/splice/file.yaml"),
        LocalSourceReference,
    )


def test_returns_none_for_unsupported_source_form() -> None:
    assert parse_source_reference("https://example.com/file.yaml") is None
