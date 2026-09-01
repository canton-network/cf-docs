from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path

import pytest

from scripts import manage_external_snippets as author


def write_manifest(path: Path, snippets: list[dict] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "urlSubstitutions": {"https://example.invalid": "replacement"},
                "snippets": snippets or [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def authoring_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    real_helper = author.helper_path()
    root = tmp_path / "cf-docs"
    helper = root / "scripts" / "helpers" / "generateOutputDocs.js"
    helper.parent.mkdir(parents=True)
    shutil.copy2(real_helper, helper)
    manifest = root / "config" / "snippet-config" / "splice-snippet-list-remote.json"
    write_manifest(manifest)
    source_dir = tmp_path / "splice"
    (source_dir / ".git").mkdir(parents=True)
    monkeypatch.setattr(author, "CF_DOCS_ROOT", root)
    return root, manifest, source_dir


def test_add_full_file_updates_manifest_renders_output_and_prints_usage(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    source = source_dir / "examples" / "hello.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('hello')\n", encoding="utf-8")

    result = author.main(
        [
            "add",
            "splice",
            "--source-dir",
            str(source_dir),
            "--source",
            "examples/hello.py",
        ]
    )

    name = "splice-literal-full-examples-hello"
    assert result == 0
    entry = json.loads(manifest.read_text(encoding="utf-8"))["snippets"][0]
    assert entry == {
        "snippetName": name,
        "sourceRepo": "splice",
        "sourceFilepath": "examples/hello.py",
        "location": {"type": "fullFile"},
        "description": "",
        "options": {"language": "python"},
    }
    output = (
        root / "docs-main" / "snippets" / "external" / "splice" / "main" / f"{name}.mdx"
    )
    assert output.read_text(encoding="utf-8") == "```python\nprint('hello')\n```"
    captured = capsys.readouterr()
    assert (
        "import ExternalSpliceMainSpliceLiteralFullExamplesHello from "
        "'/snippets/external/splice/main/splice-literal-full-examples-hello.mdx';"
    ) in captured.out
    assert "<ExternalSpliceMainSpliceLiteralFullExamplesHello />" in captured.out


def test_add_marker_expands_pair_and_rejects_duplicate_source(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, manifest, source_dir = authoring_fixture
    source = source_dir / "values.yaml"
    source.write_text(
        "before\n# DEMO_START\nenabled: true\n# DEMO_END\nafter\n",
        encoding="utf-8",
    )
    arguments = [
        "add",
        "splice",
        "--source-dir",
        str(source_dir),
        "--source",
        "values.yaml",
        "--marker",
        "DEMO",
    ]

    assert author.main(arguments) == 0
    original = manifest.read_bytes()
    assert author.main(arguments) == 1

    entry = json.loads(original)["snippets"][0]
    assert entry["location"] == {
        "type": "stringMarker",
        "start": "DEMO_START",
        "end": "DEMO_END",
    }
    assert manifest.read_bytes() == original
    assert "Snippet name already exists" in capsys.readouterr().err


def test_add_does_not_write_when_marker_validation_fails(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    source = source_dir / "values.yaml"
    source.write_text("enabled: true\n", encoding="utf-8")
    original = manifest.read_bytes()

    result = author.main(
        [
            "add",
            "splice",
            "--source-dir",
            str(source_dir),
            "--source",
            "values.yaml",
            "--marker",
            "MISSING",
        ]
    )

    assert result == 1
    assert manifest.read_bytes() == original
    assert not (root / "docs-main").exists()
    assert "Marker not found" in capsys.readouterr().err


def test_add_refuses_to_overwrite_an_orphaned_output(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    source = source_dir / "example.py"
    source.write_text("print('new')\n", encoding="utf-8")
    output = (
        root
        / "docs-main"
        / "snippets"
        / "external"
        / "splice"
        / "main"
        / "splice-literal-full-example.mdx"
    )
    output.parent.mkdir(parents=True)
    output.write_text("existing\n", encoding="utf-8")
    original_manifest = manifest.read_bytes()

    result = author.main(
        [
            "add",
            "splice",
            "--source-dir",
            str(source_dir),
            "--source",
            "example.py",
        ]
    )

    assert result == 1
    assert manifest.read_bytes() == original_manifest
    assert output.read_text(encoding="utf-8") == "existing\n"
    assert "Refusing to overwrite" in capsys.readouterr().err


def test_edit_preserves_name_and_regenerates_output(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    name = "stable-example"
    write_manifest(
        manifest,
        [
            {
                "snippetName": name,
                "sourceRepo": "splice",
                "sourceFilepath": "old.yaml",
                "location": {"type": "fullFile"},
                "description": "keep this",
                "options": {"language": "yaml", "normalizeIndent": False},
            }
        ],
    )
    source = source_dir / "new.yaml"
    source.write_text(
        "# CURRENT_START\n  nested: true\n# CURRENT_END\n",
        encoding="utf-8",
    )

    manifest.chmod(0o640)
    result = author.main(
        [
            "edit",
            "splice",
            name,
            "--source-dir",
            str(source_dir),
            "--source",
            "new.yaml",
            "--marker",
            "CURRENT",
        ]
    )

    assert result == 0
    entry = json.loads(manifest.read_text(encoding="utf-8"))["snippets"][0]
    assert entry["snippetName"] == name
    assert entry["sourceFilepath"] == "new.yaml"
    assert entry["location"] == {
        "type": "stringMarker",
        "start": "CURRENT_START",
        "end": "CURRENT_END",
    }
    assert entry["description"] == "keep this"
    assert entry["options"] == {"language": "yaml", "normalizeIndent": False}
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o640
    output = (
        root / "docs-main" / "snippets" / "external" / "splice" / "main" / f"{name}.mdx"
    )
    assert output.read_text(encoding="utf-8") == "```yaml\n  nested: true\n```"
    assert "its import path is unchanged" in capsys.readouterr().out


@pytest.mark.parametrize("version", ["", "..", "candidate/next", "candidate\\next"])
def test_version_must_be_one_safe_path_segment(version: str) -> None:
    with pytest.raises(author.SnippetAuthoringError):
        author.validate_version(version)
