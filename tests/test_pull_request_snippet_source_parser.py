from __future__ import annotations

import pytest

from scripts.snippets.references import parse_pull_request_source


def test_parses_canonical_github_pull_request_url() -> None:
    reference = parse_pull_request_source(
        "https://github.com/canton-network/splice/pull/6123"
    )

    assert reference is not None
    assert reference.repository == "canton-network/splice"
    assert reference.pull_request == 6123


@pytest.mark.parametrize(
    "value",
    [
        "https://gitlab.com/canton-network/splice/pull/6123",
        "https://github.com/canton-network/splice/pull/0",
        "https://github.com/canton-network/splice/pull/abc",
        "https://github.com/canton-network/splice/pull/6123/",
        "https://github.com/canton-network/splice/pull/6123/files",
        "https://github.com/canton-network/splice/pull/6123?tab=files",
    ],
)
def test_rejects_noncanonical_pull_request_urls(value: str) -> None:
    assert parse_pull_request_source(value) is None
