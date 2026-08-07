from __future__ import annotations

import pytest

from scripts.snippets.validation import is_safe_source_path


@pytest.mark.parametrize(
    "value",
    [
        "apps/validator-values.yaml",
        "README.md",
        "docs/path with spaces/example.rst",
    ],
)
def test_accepts_repository_relative_paths(value: str) -> None:
    assert is_safe_source_path(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/etc/passwd",
        "../secret",
        "docs/../../secret",
        "docs\\example.yaml",
        "C:\\example.yaml",
    ],
)
def test_rejects_paths_that_can_escape_or_change_separator(value: str) -> None:
    assert not is_safe_source_path(value)
