from __future__ import annotations

import pytest

from scripts.snippets.validation import is_safe_language


@pytest.mark.parametrize(
    "value",
    ["yaml", "typescript", "c++", "objective-c", "proto3", "none"],
)
def test_accepts_safe_language_tokens(value: str) -> None:
    assert is_safe_language(value)


@pytest.mark.parametrize(
    "value",
    [None, 3, "", "two words", "yaml\n```", "<script>"],
)
def test_rejects_missing_or_unsafe_language_tokens(
    value: str | int | None,
) -> None:
    assert not is_safe_language(value)
