from __future__ import annotations

import json
from pathlib import Path

from scripts.snippets.file_validation import validate_authored_files

COMMIT = "2c941ea9e834d7602d388f3271c0f864025ea756"


def write_registry(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "repositories": {
                    "canton-network/splice": {
                        "url": "https://github.com/canton-network/splice",
                        "defaultBranch": "main",
                        "visibility": "public",
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_discovers_and_validates_authored_source_files(tmp_path: Path) -> None:
    registry = tmp_path / "repositories.json"
    write_registry(registry)
    docs = tmp_path / "docs"
    docs.mkdir()
    valid = docs / "valid.source.mdx"
    invalid = docs / "invalid.source.mdx"
    ignored = docs / "ordinary.mdx"
    valid.write_text(
        f'<Snippet source="https://github.com/canton-network/splice/blob/{COMMIT}/file.yaml" '
        'language="yaml" />',
        encoding="utf-8",
    )
    invalid.write_text(
        f'<Snippet source="https://github.com/unknown/repository/blob/{COMMIT}/file.yaml" '
        'language="yaml" />',
        encoding="utf-8",
    )
    ignored.write_text('<Snippet source="invalid" />', encoding="utf-8")

    diagnostics = validate_authored_files([docs], registry_path=registry)

    assert len(diagnostics) == 1
    assert diagnostics[0].path == invalid.resolve()
    assert diagnostics[0].code == "SNIP009"


def test_allows_local_refs_only_when_preview_is_explicit(tmp_path: Path) -> None:
    registry = tmp_path / "repositories.json"
    write_registry(registry)
    page = tmp_path / "page.source.mdx"
    page.write_text(
        '<Snippet source="local://canton-network/splice/file.yaml" '
        'language="yaml" />',
        encoding="utf-8",
    )

    committed = validate_authored_files([page], registry_path=registry)
    preview = validate_authored_files(
        [page], registry_path=registry, allow_local=True
    )

    assert [diagnostic.code for diagnostic in committed] == ["SNIP007"]
    assert preview == ()
