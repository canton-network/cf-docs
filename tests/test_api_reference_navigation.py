from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_api_reference_landing_page_is_dropdown_root_and_index_page() -> None:
    docs = json.loads((REPO_ROOT / "docs-main" / "docs.json").read_text(encoding="utf-8"))
    dropdowns = docs["navigation"]["dropdowns"]
    api_reference = next(item for item in dropdowns if item["dropdown"] == "API Reference")

    assert api_reference["root"] == "api-reference"
    assert api_reference["pages"][0] == "api-reference"
    assert any(
        isinstance(item, dict) and item.get("group") == "Ledger API"
        for item in api_reference["pages"]
    )

    frontmatter = (REPO_ROOT / "docs-main" / "api-reference.mdx").read_text(encoding="utf-8")
    assert 'sidebarTitle: "api reference index"' in frontmatter


def test_site_uses_small_nav_logo_assets() -> None:
    docs = json.loads((REPO_ROOT / "docs-main" / "docs.json").read_text(encoding="utf-8"))

    assert docs["favicon"] == "/images/canton-logo-dark.svg"
    assert docs["logo"]["light"] == "/images/canton-nav-logo-dark.svg"
    assert docs["logo"]["dark"] == "/images/canton-nav-logo-white.svg"

    for logo_path in docs["logo"]["light"], docs["logo"]["dark"]:
        svg_path = REPO_ROOT / "docs-main" / logo_path.removeprefix("/")
        assert svg_path.exists()
        svg = svg_path.read_text(encoding="utf-8")
        assert 'width="150"' in svg
        assert "<text" in svg
