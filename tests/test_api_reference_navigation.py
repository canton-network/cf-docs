from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_api_reference_landing_page_is_dropdown_root_and_index_page() -> None:
    docs = json.loads((REPO_ROOT / "docs-main" / "docs.json").read_text(encoding="utf-8"))
    products = docs["navigation"]["products"]
    api_reference = next(item for item in products if item["product"] == "API Reference")

    assert api_reference["root"] == "api-reference"
    assert api_reference["pages"][0] == "api-reference"
    assert any(
        isinstance(item, dict) and item.get("group") == "Ledger API"
        for item in api_reference["pages"]
    )

    frontmatter = (REPO_ROOT / "docs-main" / "api-reference.mdx").read_text(encoding="utf-8")
    assert 'sidebarTitle: "API Reference Index"' in frontmatter


def test_product_selector_has_visible_accent_line() -> None:
    styles = (REPO_ROOT / "docs-main" / "styles.css").read_text(encoding="utf-8")

    assert ".nav-dropdown-products-selector-trigger" in styles
    assert "--canton-product-selector-line-active: #734BE2;" in styles
    assert "box-shadow: inset 0 0 0 2px var(--canton-product-selector-line-active)" in styles
