from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts import generate_external_snippets as generator


def test_copy_helper_and_config_copies_helper(tmp_path: Path) -> None:
    source_dir = tmp_path / "splice"
    helper = generator.copy_helper_and_config(
        generator.REPOS["splice"],
        source_dir,
        dry_run=False,
    )

    target_scripts = source_dir / "scripts" / "docs"
    assert helper == target_scripts / "generateOutputDocs.js"
    assert helper.is_file()
    assert (target_scripts / "exportConfig.json").is_file()


def test_copy_helper_and_config_preserves_repo_specific_helper_name(tmp_path: Path) -> None:
    source_dir = tmp_path / "splice-wallet-kernel"
    helper = generator.copy_helper_and_config(
        generator.REPOS["splice-wallet-kernel"],
        source_dir,
        dry_run=False,
    )

    target_scripts = source_dir / "scripts" / "docs"
    assert helper == target_scripts / "generateOutputDocs.cjs"
    assert helper.is_file()


def test_validate_inputs_reports_missing_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_root = tmp_path / "cf-docs"
    fake_config = fake_root / "config" / "snippet-config"
    fake_config.mkdir(parents=True)
    (fake_config / "splice-snippet-list-remote.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(generator, "CF_DOCS_ROOT", fake_root)

    with pytest.raises(SystemExit) as error:
        generator.validate_inputs(generator.REPOS["splice"])

    assert "generateOutputDocs.js" in str(error.value)


def test_copy_output_targets_docs_main_snippets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "splice"
    docs_output = source_dir / "docs-output"
    docs_output.mkdir(parents=True)
    (docs_output / "example.mdx").write_text("content", encoding="utf-8")
    fake_root = tmp_path / "cf-docs"

    monkeypatch.setattr(generator, "CF_DOCS_ROOT", fake_root)

    target = generator.copy_output(
        generator.REPOS["splice"],
        source_dir,
        version="main",
        replace=False,
        dry_run=False,
    )

    assert target == fake_root / "docs-main" / "snippets" / "external" / "splice" / "main"
    assert (target / "example.mdx").read_text(encoding="utf-8") == "content"
    assert not (fake_root / "snippets").exists()


def test_splice_snippets_are_yaml_string_markers() -> None:
    config = json.loads(
        (
            generator.CF_DOCS_ROOT
            / "config"
            / "snippet-config"
            / "splice-snippet-list-remote.json"
        ).read_text(encoding="utf-8")
    )

    for snippet in config["snippets"]:
        assert snippet["sourceRepo"] == "splice"
        assert Path(snippet["sourceFilepath"]).suffix in {".yaml", ".yml"}
        assert snippet["location"]["type"] == "stringMarker"
        assert snippet["location"]["start"]
        assert snippet["location"]["end"]
        assert snippet["options"]["language"] == "yaml"


def test_wrapper_copies_helper_runs_extraction_and_copies_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_helper = generator.helper_path()
    fake_root = tmp_path / "cf-docs"
    fake_helper = fake_root / "scripts" / "helpers" / "generateOutputDocs.js"
    fake_config = fake_root / "config" / "snippet-config" / "test-snippet-list.json"
    source_dir = tmp_path / "source"

    fake_helper.parent.mkdir(parents=True)
    shutil.copy2(real_helper, fake_helper)
    fake_config.parent.mkdir(parents=True)
    fake_config.write_text(
        """{
  "snippets": [
    {
      "snippetName": "example",
      "sourceRepo": "test",
      "sourceFilepath": "docs/example.txt",
      "location": {
        "type": "stringMarker",
        "start": "SNIPPET_START",
        "end": "SNIPPET_END"
      },
      "options": {
        "language": "text"
      }
    }
  ]
}
""",
        encoding="utf-8",
    )
    (source_dir / "docs").mkdir(parents=True)
    (source_dir / "docs" / "example.txt").write_text(
        "before\nSNIPPET_START\nhello\nSNIPPET_END\nafter\n",
        encoding="utf-8",
    )

    repo = generator.SnippetRepo(
        name="test",
        config_name="test-snippet-list.json",
        aliases=("test",),
    )
    monkeypatch.setattr(generator, "CF_DOCS_ROOT", fake_root)

    helper = generator.copy_helper_and_config(repo, source_dir, dry_run=False)
    generator.run_extraction(source_dir, helper, quiet=True, dry_run=False)
    target = generator.copy_output(
        repo,
        source_dir,
        version="main",
        replace=False,
        dry_run=False,
    )

    assert (source_dir / "docs-output" / "example.mdx").read_text(encoding="utf-8") == (
        "```text\nhello\n```"
    )
    assert (target / "example.mdx").read_text(encoding="utf-8") == "```text\nhello\n```"
