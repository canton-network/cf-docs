from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.snippets import author
from scripts.snippets.parser import parse_page

REPOSITORY = "canton-network/splice"
REPOSITORIES = {
    REPOSITORY: {
        "url": f"https://github.com/{REPOSITORY}",
        "defaultBranch": "main",
    }
}


def make_checkout(tmp_path: Path) -> Path:
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
            f"git@github.com:{REPOSITORY}.git",
        ],
        check=True,
    )
    source = checkout / "apps" / "validator-values.yaml"
    source.parent.mkdir()
    source.write_text("# SWEEP_START\nsweep: true\n# SWEEP_END\n", encoding="utf-8")
    return checkout


def test_add_scaffolds_and_checks_a_local_marker_snippet(
    tmp_path: Path, capsys
) -> None:
    checkout = make_checkout(tmp_path)

    result = author.main(
        [
            "add",
            "--source",
            "apps/validator-values.yaml",
            "--local-checkout",
            str(checkout),
            "--marker",
            "SWEEP",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert f'source="local://{REPOSITORY}/apps/validator-values.yaml"' in captured.out
    assert 'startAfter="SWEEP_START"' in captured.out
    assert 'endBefore="SWEEP_END"' in captured.out
    assert 'language="yaml"' in captured.out
    assert "Preview-only local ref" in captured.err


def test_resolve_local_rewrites_only_when_candidate_matches_condition(
    tmp_path: Path,
) -> None:
    page = tmp_path / "validator.source.mdx"
    page.write_text(
        f"""<IfVersion repository="https://github.com/{REPOSITORY}" containsPullRequest={{6123}}>
New prose.
<Snippet source="local://{REPOSITORY}/apps/validator-values.yaml" language="yaml" />
<Else>
Old prose.
</Else>
</IfVersion>
""",
        encoding="utf-8",
    )

    result = author.main(
        [
            "resolve-local",
            "--page",
            str(page),
            "--pull-request",
            "6123",
            "--skip-source-check",
        ]
    )

    rewritten = page.read_text(encoding="utf-8")
    assert result == 0
    assert "local://" not in rewritten
    assert f'source="https://github.com/{REPOSITORY}/pull/6123"' in rewritten
    assert 'path="apps/validator-values.yaml"' in rewritten
    parsed = parse_page(rewritten, path=page, repositories=REPOSITORIES)
    assert parsed.snippets[0].source.pull_request == 6123


def test_resolve_local_leaves_page_unchanged_without_matching_condition(
    tmp_path: Path, capsys
) -> None:
    page = tmp_path / "validator.source.mdx"
    original = f'<Snippet source="local://{REPOSITORY}/apps/a.yaml" language="yaml" />'
    page.write_text(original, encoding="utf-8")

    result = author.main(
        [
            "resolve-local",
            "--page",
            str(page),
            "--pull-request",
            "6123",
            "--skip-source-check",
        ]
    )

    assert result == 1
    assert "SNIP027" in capsys.readouterr().err
    assert page.read_text(encoding="utf-8") == original
