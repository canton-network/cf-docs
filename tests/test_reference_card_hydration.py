from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
def test_checked_in_docs_do_not_wrap_reference_cards_in_links() -> None:
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "docs-main").rglob("*.mdx")
        if '<a class="x2mdx-ref-card"' in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
