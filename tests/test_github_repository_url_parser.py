from __future__ import annotations

import pytest

from scripts.snippets.references import parse_github_repository_url


@pytest.mark.parametrize(
    "value",
    [
        "https://github.com/canton-network/splice",
        "https://github.com/canton-network/splice/",
    ],
)
def test_parses_complete_github_repository_url(value: str) -> None:
    assert parse_github_repository_url(value) == "canton-network/splice"


@pytest.mark.parametrize(
    "value",
    [
        "canton-network/splice",
        "https://gitlab.com/canton-network/splice",
        "https://github.com/canton-network",
        "https://github.com/canton-network/splice/tree/main",
        "https://github.com/canton-network/splice?tab=readme",
    ],
)
def test_rejects_nonrepository_or_incomplete_urls(value: str) -> None:
    assert parse_github_repository_url(value) is None
