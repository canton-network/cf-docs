from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import generate_external_snippets as generator


def run_generate_output_docs(
    tmp_path: Path,
    *,
    snippets: list[dict],
    sources: dict[str, str],
    extra_config: dict | None = None,
    extra_args: list[str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    helper = tmp_path / "generateOutputDocs.js"
    shutil.copy2(generator.helper_path(), helper)
    repo_root = tmp_path / "repo"
    output_dir = tmp_path / "docs-output"
    config_path = tmp_path / "exportConfig.json"
    for relative, content in sources.items():
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    config = {"snippets": snippets, **(extra_config or {})}
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = subprocess.run(
        [
            "node",
            str(helper),
            "--repo-root",
            str(repo_root),
            "--export-config",
            str(config_path),
            "--output",
            str(output_dir),
            *(extra_args or []),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result, output_dir


def read_output(output_dir: Path, snippet_name: str) -> str:
    return (output_dir / f"{snippet_name}.mdx").read_text(encoding="utf-8")


def test_copy_helper_and_config_copies_helper(tmp_path: Path) -> None:
    source_dir = tmp_path / "daml-shell"
    helper = generator.copy_helper_and_config(
        generator.REPOS["daml-shell"],
        source_dir,
        dry_run=False,
    )

    target_scripts = source_dir / "scripts" / "docs"
    assert helper == target_scripts / "generateOutputDocs.js"
    assert helper.is_file()
    assert (target_scripts / "exportConfig.json").is_file()


def test_copy_helper_and_config_uses_default_scripts_subdir_for_splice(
    tmp_path: Path,
) -> None:
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
    assert generator.REPOS["splice"].scripts_subdir == "scripts/docs"


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


def test_generate_output_docs_help_and_unknown_flag(tmp_path: Path) -> None:
    helper = tmp_path / "generateOutputDocs.js"
    shutil.copy2(generator.helper_path(), helper)

    help_result = subprocess.run(
        ["node", str(helper), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "Usage: node generateOutputDocs.js" in help_result.stdout
    assert "--repo-root" in help_result.stdout
    assert "--export-config" in help_result.stdout
    assert "--output" in help_result.stdout
    assert "--verbose" in help_result.stdout

    unknown = subprocess.run(
        ["node", str(helper), "--bogus"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert unknown.returncode == 1
    assert "Unknown argument: --bogus" in unknown.stderr


def test_generate_output_docs_location_indent_transform_and_cli(tmp_path: Path) -> None:
    snippets = [
        {
            "snippetName": "lines-default-indent",
            "sourceFilepath": "docs/indent.conf",
            "location": {"type": "lines", "start": 1, "end": 3},
            "options": {"language": "conf"},
        },
        {
            "snippetName": "lines-preserve-indent",
            "sourceFilepath": "docs/indent.conf",
            "location": {"type": "lines", "start": 1, "end": 3},
            "options": {"language": "conf", "normalizeIndent": False},
        },
        {
            "snippetName": "lines-baseline-indent",
            "sourceFilepath": "docs/indent.conf",
            "location": {"type": "lines", "start": 1, "end": 3},
            "options": {"language": "conf", "normalizeIndent": "baseline"},
        },
        {
            "snippetName": "bash-false-uses-baseline",
            "sourceFilepath": "docs/bash.sh",
            "location": {"type": "lines", "start": 1, "end": 1},
            "options": {"language": "bash", "normalizeIndent": False},
        },
        {
            "snippetName": "json-index-single",
            "sourceFilepath": "docs/items.json",
            "location": {"type": "jsonIndex", "start": 1, "end": 1},
            "options": {"language": "text", "normalizeIndent": False},
        },
        {
            "snippetName": "json-index-range",
            "sourceFilepath": "docs/items.json",
            "location": {"type": "jsonIndex", "start": 0, "end": 1},
            "options": {"language": "text", "normalizeIndent": False},
        },
        {
            "snippetName": "full-file",
            "sourceFilepath": "docs/full.yaml",
            "location": {"type": "fullFile"},
            "options": {"language": "yaml"},
        },
        {
            "snippetName": "regex-wrap",
            "sourceFilepath": "docs/regex.txt",
            "location": {"type": "regexWrap", "start": "BEGIN", "end": "END"},
            "options": {"language": "text", "normalizeIndent": False},
        },
        {
            "snippetName": "language-none",
            "sourceFilepath": "docs/plain.txt",
            "location": {"type": "lines", "start": 1, "end": 1},
            "options": {"language": "none", "normalizeIndent": False},
        },
        {
            "snippetName": "unescape-rst-quotes",
            "sourceFilepath": "docs/console.txt",
            "location": {"type": "lines", "start": 1, "end": 1},
            "options": {
                "language": "haskell",
                "normalizeIndent": False,
                "unescapeRstQuotes": True,
            },
        },
        {
            "snippetName": "rstinclude-warning",
            "sourceFilepath": "docs/include.rst",
            "location": {"type": "fullFile"},
            "options": {"transform": "rstinclude"},
        },
        {
            "snippetName": "rstjson-code-block",
            "sourceFilepath": "docs/sphinx.json.rst",
            "location": {"type": "fullFile"},
            "options": {"transform": "rstjson", "language": "python"},
        },
        {
            "snippetName": "url-substituted",
            "sourceFilepath": "docs/urls.txt",
            "location": {"type": "fullFile"},
            "options": {"language": "text", "normalizeIndent": False},
        },
    ]
    sources = {
        "docs/indent.conf": "    canton {\n      storage = memory\n    }\n",
        "docs/bash.sh": "    echo hi\n",
        "docs/items.json": '["alpha", "beta", "gamma"]\n',
        "docs/full.yaml": "    foo: 1\n    bar: 2\n",
        "docs/regex.txt": "prefix BEGIN\nhello\nEND suffix\n",
        "docs/plain.txt": "plain body\n",
        "docs/console.txt": "participant.dars.upload(\\'file.dar\\')\n",
        "docs/include.rst": (
            ".. Copyright (c) 2026\n"
            "\n"
            ".. warning::\n"
            "\n"
            "   Do not skip :ref:`the guide <guide>`.\n"
        ),
        "docs/sphinx.json.rst": (
            "prefix\n"
            ".. code-block:: python\n"
            "\n"
            "    print(\"hi\")\n"
            "    print(\"there\")\n"
            "after\n"
        ),
        "docs/urls.txt": "# see https://docs.daml.com/old\n",
    }

    result, output_dir = run_generate_output_docs(
        tmp_path,
        snippets=snippets,
        sources=sources,
        extra_config={
            "rstIncludeRefTargets": {"guide": "/docs/guide"},
            "urlSubstitutions": {
                "https://docs.daml.com/old": "https://docs.canton.network/new"
            },
        },
        extra_args=["--verbose"],
    )

    assert result.returncode == 0, result.stderr
    assert "Processing snippet: lines-default-indent" in result.stdout
    assert "Processing complete: 13 succeeded, 0 failed" in result.stdout

    assert read_output(output_dir, "lines-default-indent") == (
        "```conf\n  canton {\n    storage = memory\n  }\n```"
    )
    assert read_output(output_dir, "lines-preserve-indent") == (
        "```conf\n    canton {\n      storage = memory\n    }\n```"
    )
    assert read_output(output_dir, "lines-baseline-indent") == (
        "```conf\ncanton {\n  storage = memory\n}\n```"
    )
    assert read_output(output_dir, "bash-false-uses-baseline") == "```bash\necho hi\n```"
    assert read_output(output_dir, "json-index-single") == "```text\nbeta\n```"
    assert read_output(output_dir, "json-index-range") == "```text\nalpha\nbeta\n```"
    assert read_output(output_dir, "full-file") == "```yaml\nfoo: 1\nbar: 2\n```"
    assert read_output(output_dir, "regex-wrap") == "```text\nhello\n```"
    assert read_output(output_dir, "language-none") == "```\nplain body\n```"
    assert read_output(output_dir, "unescape-rst-quotes") == (
        "```haskell\nparticipant.dars.upload('file.dar')\n```"
    )
    assert read_output(output_dir, "rstinclude-warning") == (
        "<Warning>\n\nDo not skip [the guide](/docs/guide).\n\n</Warning>"
    )
    assert read_output(output_dir, "rstjson-code-block") == (
        "```python\nprint(\"hi\")\nprint(\"there\")\n```"
    )
    assert read_output(output_dir, "url-substituted") == (
        "```text\n# see https://docs.canton.network/new\n```"
    )


def test_generate_output_docs_reports_extraction_errors(tmp_path: Path) -> None:
    snippets = [
        {
            "snippetName": "missing-marker",
            "sourceFilepath": "docs/example.txt",
            "location": {
                "type": "stringMarker",
                "start": "MISSING_START",
                "end": "MISSING_END",
            },
            "options": {"language": "text"},
        },
        {
            "snippetName": "oob-lines",
            "sourceFilepath": "docs/example.txt",
            "location": {"type": "lines", "start": 1, "end": 99},
            "options": {"language": "text"},
        },
        {
            "snippetName": "invalid-json-index",
            "sourceFilepath": "docs/not-array.json",
            "location": {"type": "jsonIndex", "start": 0, "end": 0},
            "options": {"language": "text"},
        },
        {
            "snippetName": "good-snippet",
            "sourceFilepath": "docs/example.txt",
            "location": {"type": "lines", "start": 1, "end": 1},
            "options": {"language": "text", "normalizeIndent": False},
        },
    ]
    result, output_dir = run_generate_output_docs(
        tmp_path,
        snippets=snippets,
        sources={
            "docs/example.txt": "hello\n",
            "docs/not-array.json": '{"not": "an-array"}\n',
        },
    )

    assert result.returncode == 1
    assert "Start marker not found: \"MISSING_START\"" in result.stderr
    assert "Line numbers out of range" in result.stderr
    assert "JSON root must be an array for location type jsonIndex" in result.stderr
    assert "Processing complete: 1 succeeded, 3 failed" in result.stdout
    assert read_output(output_dir, "good-snippet") == "```text\nhello\n```"
    assert not (output_dir / "missing-marker.mdx").exists()
    assert not (output_dir / "oob-lines.mdx").exists()
    assert not (output_dir / "invalid-json-index.mdx").exists()
