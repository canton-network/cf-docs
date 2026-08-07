from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.snippets.validate import main


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


def test_returns_zero_and_page_count_for_valid_sources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = tmp_path / "repositories.json"
    write_registry(registry)
    page = tmp_path / "page.source.mdx"
    page.write_text("Ordinary prose.", encoding="utf-8")

    result = main([str(page), "--registry", str(registry)])

    assert result == 0
    assert capsys.readouterr().out == "Validated 1 authored snippet page(s)\n"


def test_returns_one_and_prints_actionable_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = tmp_path / "repositories.json"
    write_registry(registry)
    page = tmp_path / "page.source.mdx"
    page.write_text(
        '<Snippet source="local://canton-network/splice/file.yaml" '
        'language="yaml" />',
        encoding="utf-8",
    )

    result = main([str(page), "--registry", str(registry)])
    error = capsys.readouterr().err

    assert result == 1
    assert f"{page.resolve()}:1:1: SNIP007" in error
    assert "snippets:resolve-local" in error


def test_allow_local_switch_enables_preview_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = tmp_path / "repositories.json"
    write_registry(registry)
    page = tmp_path / "page.source.mdx"
    page.write_text(
        '<Snippet source="local://canton-network/splice/file.yaml" '
        'language="yaml" />',
        encoding="utf-8",
    )

    result = main(
        [str(page), "--registry", str(registry), "--allow-local"]
    )

    assert result == 0
    assert "Validated 1" in capsys.readouterr().out
