from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import manage_external_snippets as author
from scripts import snippet_repos


def test_canton_docs_cn_imports_have_manifest_destinations() -> None:
    """Historical snippet names must still match their configured destinations."""
    config = json.loads(author.manifest_path(snippet_repos.REPOS["canton"]).read_text())
    destinations = {snippet["snippetName"] for snippet in config["snippets"]}
    imports = {
        name
        for page in (snippet_repos.CF_DOCS_ROOT / "docs-main").rglob("*.mdx")
        for name in re.findall(
            r"from [\"']/snippets/external/canton/main/"
            r"(docs-open/target/snippet_json_data/docs-cn/[^\"']+)\.mdx[\"']",
            page.read_text(encoding="utf-8"),
        )
    }

    assert imports
    assert not imports - destinations


def run_generate_output_docs(
    tmp_path: Path,
    *,
    snippets: list[dict],
    sources: dict[str, str],
    extra_config: dict | None = None,
    extra_args: list[str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    helper = tmp_path / "generateOutputDocs.js"
    shutil.copy2(author.helper_path(), helper)
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


def _write_string_marker_fixture(
    tmp_path: Path, source_text: str, *, normalize_indent: bool | None = None
) -> tuple[Path, Path]:
    source_dir = tmp_path / "source"
    helper = source_dir / "scripts" / "docs" / "generateOutputDocs.js"
    config = helper.parent / "exportConfig.json"
    source = source_dir / "docs" / "example.txt"

    helper.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    shutil.copy2(author.helper_path(), helper)
    options: dict[str, object] = {"language": "text"}
    if normalize_indent is not None:
        options["normalizeIndent"] = normalize_indent
    config.write_text(
        json.dumps(
            {
                "snippets": [
                    {
                        "snippetName": "example",
                        "sourceFilepath": "docs/example.txt",
                        "location": {
                            "type": "stringMarker",
                            "start": "SNIPPET_START",
                            "end": "SNIPPET_END",
                        },
                        "options": options,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    source.write_text(source_text, encoding="utf-8")
    return source_dir, helper


def test_string_marker_preserves_first_line_indentation(tmp_path: Path) -> None:
    source_dir, helper = _write_string_marker_fixture(
        tmp_path,
        "before\nSNIPPET_START\n\n    first\n        second\n\nSNIPPET_END\nafter\n",
        normalize_indent=False,
    )

    subprocess.run(["node", helper], cwd=source_dir, capture_output=True, check=True)

    assert (source_dir / "docs-output" / "example.mdx").read_text(
        encoding="utf-8"
    ) == "```text\n    first\n        second\n```"


@pytest.mark.parametrize("duplicate_marker", ["SNIPPET_START", "SNIPPET_END"])
def test_string_marker_rejects_duplicate_markers(
    tmp_path: Path, duplicate_marker: str
) -> None:
    source_dir, helper = _write_string_marker_fixture(
        tmp_path,
        "\n".join(
            [
                "SNIPPET_START",
                "content",
                "SNIPPET_END",
                duplicate_marker,
                "",
            ]
        ),
    )

    result = subprocess.run(
        ["node", helper],
        cwd=source_dir,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert f'Marker must appear exactly once, found 2: "{duplicate_marker}"' in (
        result.stderr
    )


def test_generate_output_docs_help_and_unknown_flag(tmp_path: Path) -> None:
    helper = tmp_path / "generateOutputDocs.js"
    shutil.copy2(author.helper_path(), helper)

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
    assert "Marker not found: \"MISSING_START\"" in result.stderr
    assert "Line numbers out of range" in result.stderr
    assert "JSON root must be an array for location type jsonIndex" in result.stderr
    assert "Processing complete: 1 succeeded, 3 failed" in result.stdout
    assert read_output(output_dir, "good-snippet") == "```text\nhello\n```"
    assert not (output_dir / "missing-marker.mdx").exists()
    assert not (output_dir / "oob-lines.mdx").exists()
    assert not (output_dir / "invalid-json-index.mdx").exists()


def test_discover_repos_derives_one_repo_per_remote_manifest(tmp_path: Path) -> None:
    for name in ("canton", "dpm"):
        (tmp_path / f"{name}-snippet-list-remote.json").write_text('{"snippets": []}', encoding="utf-8")
    (tmp_path / "snippet-list-local.json").write_text('{"snippets": []}', encoding="utf-8")

    repos = snippet_repos.discover_repos(tmp_path)

    assert sorted(repos) == ["canton", "dpm"]
    assert repos["dpm"] == snippet_repos.SnippetRepo(
        name="dpm", config_name="dpm-snippet-list-remote.json", aliases=("dpm",)
    )
    assert repos["canton"].prepare == snippet_repos.REPO_PREPARATION["canton"]
