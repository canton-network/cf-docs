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


def test_api_reference_cards_link_to_top_level_details_pages() -> None:
    page = (REPO_ROOT / "docs-main" / "api-reference.mdx").read_text(encoding="utf-8")

    expected_hrefs = {
        "Ledger API": "/reference/ledger-api/details",
        "Daml Standard Library": "/appdev/reference/daml-standard-library/index",
        "TypeScript": "/reference/typescript/details",
        "dApp API": "/reference/dapp-api/details",
        "Wallet Gateway": "/reference/wallet-gateway-json-rpc/operations/details",
        "Splice APIs": "/reference/splice-apis/details",
        "Admin API": "/reference/admin-api/details",
    }
    for title, href in expected_hrefs.items():
        assert f'<Card title="{title}" icon="bookmark" href="{href}">' in page


def test_api_reference_top_groups_expose_details_and_history_entry() -> None:
    docs = json.loads((REPO_ROOT / "docs-main" / "docs.json").read_text(encoding="utf-8"))
    api_reference = next(item for item in docs["navigation"]["dropdowns"] if item["dropdown"] == "API Reference")
    groups = {
        item["group"]: item
        for item in api_reference["pages"]
        if isinstance(item, dict) and isinstance(item.get("group"), str)
    }

    expected_details = {
        "Ledger API": "reference/ledger-api/details",
        "Daml Standard Library": "appdev/reference/daml-standard-library/index",
        "TypeScript": "reference/typescript/details",
        "dApp API": "reference/dapp-api/details",
        "Wallet Gateway": "reference/wallet-gateway-json-rpc/operations/details",
        "Splice APIs": "reference/splice-apis/details",
        "Admin API": "reference/admin-api/details",
    }
    for group, details_ref in expected_details.items():
        assert groups[group]["pages"][-1] == details_ref

        details_path = REPO_ROOT / "docs-main" / f"{details_ref}.mdx"
        assert details_path.exists()
        details_page = details_path.read_text(encoding="utf-8")
        assert 'title: "Details and history"' in details_page
        assert 'class="x2mdx-ref-hero"' in details_page
