from __future__ import annotations

import pytest

from scripts.snippets.references import parse_local_source


def test_parses_local_repository_reference() -> None:
    reference = parse_local_source(
        "local://canton-network/splice/apps/validator-values.yaml"
    )

    assert reference is not None
    assert reference.repository == "canton-network/splice"
    assert reference.path == "apps/validator-values.yaml"


@pytest.mark.parametrize(
    "value",
    [
        "file://canton-network/splice/apps/validator-values.yaml",
        "local://canton-network/validator-values.yaml",
        "local://canton-network/splice/",
        "local://canton-network/splice/file?raw=1",
        "local://canton-network/splice/file#anchor",
    ],
)
def test_rejects_incomplete_or_nonlocal_references(value: str) -> None:
    assert parse_local_source(value) is None
