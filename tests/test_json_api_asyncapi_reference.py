from __future__ import annotations

import json
from pathlib import Path

from x2mdx.history import HistoryEventKind, load_history_report, validate_history_report
from x2mdx.history.events import history_event_anchor


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs-main"
OUTPUT_ROOT = DOCS_ROOT / "reference" / "json-api-asyncapi-reference"
REPORT_PATH = OUTPUT_ROOT / "history-report.json"
SOURCE_CONFIG = (
    REPO_ROOT
    / "config"
    / "x2mdx"
    / "ledger-api-asyncapi"
    / "source-artifacts.json"
)


def test_checked_asyncapi_report_matches_configured_snapshots_and_reader_routes() -> None:
    source_config = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    report = load_history_report(REPORT_PATH)

    validate_history_report(report)
    assert report.surface_id == "json-ledger-api-asyncapi"
    assert report.comparison_versions == tuple(
        entry["version"] for entry in source_config["versions"]
    )
    assert report.publish_version == source_config["publish_version"]
    assert report.current_items()

    for item in report.current_items():
        assert item.route is not None
        page = DOCS_ROOT / f"{item.route}.mdx"
        assert page.is_file(), item.id


def test_checked_asyncapi_item_pages_use_linked_badges_and_history_last() -> None:
    report = load_history_report(REPORT_PATH)

    for item in report.current_items():
        assert item.route is not None
        text = (DOCS_ROOT / f"{item.route}.mdx").read_text(encoding="utf-8")
        added_anchor = history_event_anchor(
            HistoryEventKind.INTRODUCED,
            item.first_seen,
        )
        assert f'href="#{added_anchor}"' in text
        assert "## History" in text
        assert text.rfind("\n## ") == text.index("\n## History")
        assert "Details and history" not in text
        assert "## Lifecycle Changes" not in text

        if item.last_changed is not None:
            updated_anchor = history_event_anchor(
                HistoryEventKind.CHANGED,
                item.last_changed,
            )
            assert f'href="#{updated_anchor}"' in text


def test_checked_asyncapi_tree_and_navigation_have_no_history_pages() -> None:
    mdx_files = sorted(OUTPUT_ROOT.rglob("*.mdx"))
    assert not list(OUTPUT_ROOT.rglob("details.mdx"))
    assert all("Details and history" not in path.read_text(encoding="utf-8") for path in mdx_files)

    docs = json.loads((DOCS_ROOT / "docs.json").read_text(encoding="utf-8"))
    navigation_text = json.dumps(docs["navigation"])
    assert "json-api-asyncapi-reference/operations/details" not in navigation_text
    assert "json-api-asyncapi-reference/operations/" in navigation_text
    assert "json-api-asyncapi-reference/channels/" in navigation_text

    redirect_sources = {
        redirect["source"]
        for redirect in docs["redirects"]
        if redirect["source"].startswith(
            "/reference/json-api-asyncapi-reference/"
        )
    }
    assert redirect_sources == {
        "/reference/json-api-asyncapi-reference/operations/details",
        *{
            "/reference/json-api-asyncapi-reference/operations/"
            f"{channel_page.stem}/details"
            for channel_page in (OUTPUT_ROOT / "channels").glob("*.mdx")
        },
    }
