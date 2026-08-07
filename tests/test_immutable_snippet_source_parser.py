from __future__ import annotations

import pytest

from scripts.snippets.references import parse_immutable_source

COMMIT = "2C941EA9E834D7602D388F3271C0F864025EA756"


def test_parses_full_github_blob_url() -> None:
    reference = parse_immutable_source(
        f"https://github.com/canton-network/splice/blob/{COMMIT}/"
        "apps/validator-values.yaml"
    )

    assert reference is not None
    assert reference.repository == "canton-network/splice"
    assert reference.commit == COMMIT.lower()
    assert reference.path == "apps/validator-values.yaml"


@pytest.mark.parametrize(
    "value",
    [
        (
            "https://gitlab.com/canton-network/splice/blob/"
            f"{COMMIT}/apps/validator-values.yaml"
        ),
        (
            "https://github.com/canton-network/splice/blob/main/"
            "apps/validator-values.yaml"
        ),
        (
            "https://github.com/canton-network/splice/blob/abc123/"
            "apps/validator-values.yaml"
        ),
        f"https://github.com/canton-network/splice/blob/{COMMIT}/",
        f"https://github.com/canton-network/splice/blob/{COMMIT}/file?raw=1",
        f"https://github.com/canton-network/splice/blob/{COMMIT}/file#anchor",
    ],
)
def test_rejects_non_immutable_or_incomplete_urls(value: str) -> None:
    assert parse_immutable_source(value) is None
