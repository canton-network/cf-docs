from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_api_reference_landing_page_is_dropdown_root_not_sidebar_page() -> None:
    docs = json.loads((REPO_ROOT / "docs-main" / "docs.json").read_text(encoding="utf-8"))
    dropdowns = docs["navigation"]["dropdowns"]
    api_reference = next(item for item in dropdowns if item["dropdown"] == "API Reference")

    assert api_reference["root"] == "api-reference"
    assert "api-reference" not in api_reference["pages"]
    assert any(
        isinstance(item, dict) and item.get("group") == "Ledger API"
        for item in api_reference["pages"]
    )
