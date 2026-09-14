from __future__ import annotations

import json
import shutil
import stat
import subprocess
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




def commit_source(source_dir: Path, message: str = "Record source") -> str:
    subprocess.run(["git", "-C", source_dir, "add", "--all"], check=True)
    subprocess.run(["git", "-C", source_dir, "commit", "-q", "-m", message], check=True)
    commit = subprocess.run(
        ["git", "-C", source_dir, "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", source_dir, "update-ref", "refs/remotes/origin/main", commit],
        check=True,
    )
    subprocess.run(
        ["git", "-C", source_dir, "branch", "--set-upstream-to=origin/main"],
        check=True,
        capture_output=True,
    )
    return commit


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
    subprocess.run(["git", "init", "-q", "-b", "main", source_dir], check=True)
    subprocess.run(
        ["git", "-C", source_dir, "config", "user.name", "Snippet Tests"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", source_dir, "config", "user.email", "snippets@example.com"],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            source_dir,
            "remote",
            "add",
            "origin",
            "git@github.com:canton-network/splice.git",
        ],
        check=True,
    )
    monkeypatch.setattr(author, "CF_DOCS_ROOT", root)
    return root, manifest, source_dir


def test_add_full_file_updates_manifest_renders_output_and_prints_usage(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    source = source_dir / "examples" / "hello.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('hello')\n", encoding="utf-8")
    commit = commit_source(source_dir)

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
    lock = json.loads(
        (root / "config" / "snippet-config" / "snippet-source-lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock["snippets"][name] == {
        "repository": "splice",
        "commit": commit,
        "remote": "https://github.com/canton-network/splice",
        "ref": "origin/main",
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
    commit_source(source_dir)
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
    commit_source(source_dir)
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


def test_add_dry_run_prints_diffs_without_writing(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    source = source_dir / "example.py"
    source.write_text("print('preview')\n", encoding="utf-8")
    commit_source(source_dir)
    original_manifest = manifest.read_bytes()

    result = author.main(
        [
            "add",
            "splice",
            "--source-dir",
            str(source_dir),
            "--source",
            "example.py",
            "--dry-run",
        ]
    )

    assert result == 0
    assert manifest.read_bytes() == original_manifest
    assert not (root / "docs-main").exists()
    output = capsys.readouterr().out
    assert "Dry run: would add splice-literal-full-example; no files written" in output
    assert "Manifest diff:" in output
    assert '+      "snippetName": "splice-literal-full-example"' in output
    assert "Generated MDX diff:" in output
    assert "+```python" in output
    assert "+print('preview')" in output
    assert "Source lock diff:" in output
    assert '+      "commit": "' in output


def test_add_refuses_to_overwrite_an_orphaned_output(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    source = source_dir / "example.py"
    source.write_text("print('new')\n", encoding="utf-8")
    commit_source(source_dir)
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










def test_add_rejects_dirty_source_before_recording_commit(
    authoring_fixture: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, source_dir = authoring_fixture
    source = source_dir / "example.py"
    source.write_text("print('committed')\n", encoding="utf-8")
    commit_source(source_dir)
    source.write_text("print('dirty')\n", encoding="utf-8")
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
    assert not (root / "docs-main").exists()
    assert "must match HEAD" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        (
            "git@github.com:canton-network/splice.git",
            "https://github.com/canton-network/splice",
        ),
        (
            "https://github.com/canton-network/splice.git",
            "https://github.com/canton-network/splice",
        ),
        (
            "ssh://git@github.com/canton-network/splice.git",
            "https://github.com/canton-network/splice",
        ),
    ],
)
def test_normalized_remote_url(remote: str, expected: str) -> None:
    assert author.normalized_remote_url(remote) == expected
