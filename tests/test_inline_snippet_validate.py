from __future__ import annotations

import json
from pathlib import Path

from scripts.snippets import check_all
from scripts.snippets.validate import validate_pages

REPOSITORY = "canton-network/splice"


def registry(tmp_path: Path) -> Path:
    path = tmp_path / "repositories.json"
    path.write_text(
        json.dumps(
            {
                "repositories": {
                    REPOSITORY: {
                        "url": f"https://github.com/{REPOSITORY}",
                        "defaultBranch": "main",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def test_committed_local_ref_reports_exact_line_and_remediation(tmp_path: Path) -> None:
    page = tmp_path / "validator.source.mdx"
    page.write_text(
        f'prose\n<Snippet source="local://{REPOSITORY}/apps/a.yaml" language="yaml" />\n',
        encoding="utf-8",
    )

    diagnostics = validate_pages([page], registry(tmp_path))

    diagnostic = next(item for item in diagnostics if item.code == "SNIP007")
    assert diagnostic.path == page.resolve()
    assert diagnostic.line == 2
    assert diagnostic.remediation is not None
    assert "snippets:resolve-local" in diagnostic.remediation


def test_check_all_is_a_noop_before_any_page_opts_in(tmp_path: Path, capsys) -> None:
    assert check_all.main([str(tmp_path)]) == 0
    assert "Checked 0 generated snippet page(s)" in capsys.readouterr().out
