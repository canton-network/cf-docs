from __future__ import annotations

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


def _write_fixture_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_text: str,
    location: dict,
    options: dict | None = None,
) -> tuple[generator.SnippetRepo, Path]:
    import json

    real_helper = generator.helper_path()
    fake_root = tmp_path / "cf-docs"
    fake_helper = fake_root / "scripts" / "helpers" / "generateOutputDocs.js"
    fake_config = fake_root / "config" / "snippet-config" / "test-snippet-list.json"
    source_dir = tmp_path / "source"

    fake_helper.parent.mkdir(parents=True)
    shutil.copy2(real_helper, fake_helper)
    fake_config.parent.mkdir(parents=True)
    fake_config.write_text(
        json.dumps(
            {
                "snippets": [
                    {
                        "snippetName": "example",
                        "sourceRepo": "test",
                        "sourceFilepath": "docs/example.txt",
                        "location": location,
                        "options": options or {"language": "text"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (source_dir / "docs").mkdir(parents=True)
    (source_dir / "docs" / "example.txt").write_text(source_text, encoding="utf-8")

    repo = generator.SnippetRepo(
        name="test",
        config_name="test-snippet-list.json",
        aliases=("test",),
    )
    monkeypatch.setattr(generator, "CF_DOCS_ROOT", fake_root)
    return repo, source_dir


def test_string_marker_preserves_indentation_of_first_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Indented sources (e.g. RST literal blocks) must keep relative alignment.

    Regression test for the former ``.trim()`` behavior that stripped leading
    whitespace from the first content line only, misaligning multi-line
    indented snippets.
    """
    repo, source_dir = _write_fixture_repo(
        tmp_path,
        monkeypatch,
        source_text=(
            ".. code-block:: text\n"
            "   :name: marker-start\n"
            "\n"
            "   > command\n"
            "      output line\n"
            "\n"
            ".. marker-end\n"
        ),
        location={"type": "stringMarker", "start": "marker-start", "end": "marker-end"},
        options={"language": "text", "normalizeIndent": False},
    )

    helper = generator.copy_helper_and_config(repo, source_dir, dry_run=False)
    generator.run_extraction(source_dir, helper, quiet=True, dry_run=False)

    assert (source_dir / "docs-output" / "example.mdx").read_text(encoding="utf-8") == (
        "```text\n   > command\n      output line\n```"
    )


def test_string_marker_must_appear_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    repo, source_dir = _write_fixture_repo(
        tmp_path,
        monkeypatch,
        source_text="MARKER_START\nfirst\nMARKER_END\nMARKER_START\nsecond\nMARKER_END\n",
        location={"type": "stringMarker", "start": "MARKER_START", "end": "MARKER_END"},
    )

    helper = generator.copy_helper_and_config(repo, source_dir, dry_run=False)
    with pytest.raises(subprocess.CalledProcessError):
        generator.run_extraction(source_dir, helper, quiet=True, dry_run=False)


def test_internal_source_configs_have_no_line_selectors() -> None:
    """canton/daml-shell must use string markers; scribe/dpm remote configs are retired.

    Line-number selectors silently corrupt published snippets when the
    upstream source shifts. The internal-source migration replaced them with
    string markers (canton, daml-shell) or removed the remote source entirely
    (scribe and dpm transferred docs ownership to cf-docs).
    """
    import json

    config_dir = generator.CF_DOCS_ROOT / "config" / "snippet-config"

    for name in ("canton-snippet-list-remote.json", "daml-shell-snippet-list-remote.json"):
        data = json.loads((config_dir / name).read_text(encoding="utf-8"))
        lines_entries = [
            s["snippetName"]
            for s in data["snippets"]
            if s["location"]["type"] == "lines"
        ]
        assert lines_entries == [], f"{name} must not use line selectors: {lines_entries}"

    for retired in ("scribe-snippet-list-remote.json", "dpm-snippet-list-remote.json"):
        assert not (config_dir / retired).exists(), f"{retired} was retired; do not re-add it"

    lists = json.loads(
        (config_dir / "remote-snippet-lists.json").read_text(encoding="utf-8")
    )["snippetLists"]
    assert "scribe-snippet-list-remote.json" not in lists
    assert "dpm-snippet-list-remote.json" not in lists


def test_internal_source_marker_tokens_are_unique_per_source_file() -> None:
    """Marker tokens must be unique and non-overlapping within each source file."""
    import itertools
    import json

    config_dir = generator.CF_DOCS_ROOT / "config" / "snippet-config"

    for name in ("canton-snippet-list-remote.json", "daml-shell-snippet-list-remote.json"):
        data = json.loads((config_dir / name).read_text(encoding="utf-8"))
        by_file: dict[str, list[str]] = {}
        for snippet in data["snippets"]:
            location = snippet["location"]
            if location["type"] != "stringMarker":
                continue
            tokens = by_file.setdefault(snippet["sourceFilepath"], [])
            tokens.extend((location["start"], location["end"]))
        for source_file, tokens in by_file.items():
            assert len(tokens) == len(set(tokens)), (
                f"duplicate marker tokens for {source_file} in {name}"
            )
            for a, b in itertools.permutations(tokens, 2):
                assert a not in b, (
                    f"marker token {a!r} is a substring of {b!r} in {source_file}; "
                    "extraction by indexOf would match the wrong marker"
                )
