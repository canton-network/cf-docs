from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.snippets.registry import (
    RepositoryVisibility,
    load_repository_registry,
)


def write_registry(path: Path, repositories: object) -> None:
    path.write_text(
        json.dumps({"repositories": repositories}), encoding="utf-8"
    )


def test_loads_repository_identity_in_name_order(tmp_path: Path) -> None:
    path = tmp_path / "repositories.json"
    write_registry(
        path,
        {
            "digital-asset/daml": {
                "url": "https://github.com/digital-asset/daml",
                "defaultBranch": "main",
                "visibility": "public",
            },
            "DACH-NY/daml-shell": {
                "url": "https://github.com/DACH-NY/daml-shell",
                "defaultBranch": "main",
                "visibility": "private",
            },
        },
    )

    registry = load_repository_registry(path)

    assert [entry.name for entry in registry.repositories] == [
        "DACH-NY/daml-shell",
        "digital-asset/daml",
    ]
    assert registry.get("DACH-NY/daml-shell").visibility is (
        RepositoryVisibility.PRIVATE
    )
    assert registry.get("missing") is None


@pytest.mark.parametrize(
    "repositories",
    [
        {},
        {"digital-asset/daml": []},
        {
            "digital-asset/daml": {
                "url": "https://github.com/not-the/repository",
                "defaultBranch": "main",
                "visibility": "public",
            }
        },
        {
            "digital-asset/daml": {
                "url": "https://github.com/digital-asset/daml",
                "defaultBranch": "",
                "visibility": "public",
            }
        },
        {
            "digital-asset/daml": {
                "url": "https://github.com/digital-asset/daml",
                "defaultBranch": "main",
                "visibility": "internal",
            }
        },
    ],
)
def test_rejects_invalid_repository_entries(
    tmp_path: Path, repositories: object
) -> None:
    path = tmp_path / "repositories.json"
    write_registry(path, repositories)

    with pytest.raises(ValueError):
        load_repository_registry(path)


def test_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "repositories.json"
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(ValueError, match="Cannot read"):
        load_repository_registry(path)
