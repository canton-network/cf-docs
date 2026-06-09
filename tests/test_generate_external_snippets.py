from __future__ import annotations

from pathlib import Path

import pytest

from scripts import generate_external_snippets as generator


def test_copy_helper_and_config_copies_helper_dependency(tmp_path: Path) -> None:
    source_dir = tmp_path / "splice"
    helper = generator.copy_helper_and_config(
        generator.REPOS["splice"],
        source_dir,
        dry_run=False,
    )

    target_scripts = source_dir / "scripts" / "docs"
    assert helper == target_scripts / "generateOutputDocs.js"
    assert helper.is_file()
    assert (target_scripts / "rstIncludeToMdx.js").is_file()
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
    assert (target_scripts / "rstIncludeToMdx.js").is_file()


def test_validate_inputs_reports_missing_helper_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_root = tmp_path / "cf-docs"
    fake_helpers = fake_root / "scripts" / "helpers"
    fake_config = fake_root / "config" / "snippet-config"
    fake_helpers.mkdir(parents=True)
    fake_config.mkdir(parents=True)
    (fake_helpers / "generateOutputDocs.js").write_text("", encoding="utf-8")
    (fake_config / "splice-snippet-list-remote.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(generator, "CF_DOCS_ROOT", fake_root)
    monkeypatch.setattr(generator, "HELPER_SOURCE_DIR", fake_helpers)

    with pytest.raises(SystemExit) as error:
        generator.validate_inputs(generator.REPOS["splice"])

    assert "rstIncludeToMdx.js" in str(error.value)


def test_copy_output_targets_docs_main_snippets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
