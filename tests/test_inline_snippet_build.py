from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.snippets import build


REPOSITORY = "canton-network/splice"


def test_preview_renders_local_source_without_a_pr_argument(tmp_path: Path) -> None:
    checkout = tmp_path / "splice"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", checkout], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            checkout,
            "remote",
            "add",
            "origin",
            f"https://github.com/{REPOSITORY}.git",
        ],
        check=True,
    )
    source = checkout / "apps" / "example.yaml"
    source.parent.mkdir()
    source.write_text("value: local\n", encoding="utf-8")
    page = tmp_path / "validator.source.mdx"
    page.write_text(
        f'<Snippet source="local://{REPOSITORY}/apps/example.yaml" language="yaml" />',
        encoding="utf-8",
    )
    output = tmp_path / "preview.mdx"

    result = build.main(
        [
            "preview",
            "--page",
            str(page),
            "--candidate",
            "--source-dir",
            f"{REPOSITORY}={checkout}",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert "value: local" in output.read_text(encoding="utf-8")
    assert output.with_suffix(".evidence.json").is_file()


def test_preview_requires_an_explicit_release_selection(tmp_path: Path, capsys) -> None:
    page = tmp_path / "validator.source.mdx"
    page.write_text("prose", encoding="utf-8")

    result = build.main(["preview", "--page", str(page)])

    assert result == 1
    assert "Select at least one" in capsys.readouterr().err
