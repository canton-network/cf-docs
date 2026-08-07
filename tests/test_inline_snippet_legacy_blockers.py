from __future__ import annotations

from pathlib import Path

from scripts.snippets.legacy_blockers import BlockerGroup, verify_blockers
from scripts.snippets.migrate_legacy import LegacySnippet


def snippet(alias: str, name: str, location_type: str) -> LegacySnippet:
    return LegacySnippet(
        Path("manifest.json"),
        {},
        {
            "sourceRepo": alias,
            "snippetName": name,
            "sourceFilepath": "generated.json",
            "location": {"type": location_type},
            "options": {"transform": "rstjson"},
        },
    )


def test_accepts_exact_explicit_and_grouped_blocker_inventory() -> None:
    groups = [BlockerGroup("canton", "jsonIndex", "rstjson", 1, "not committed")]

    errors = verify_blockers(
        [
            snippet("canton", "generated", "jsonIndex"),
            snippet("dpm", "published-only", "lines"),
        ],
        groups,
        {"dpm:published-only": "not in history"},
    )

    assert errors == []


def test_rejects_new_or_stale_legacy_blockers() -> None:
    errors = verify_blockers(
        [snippet("quickstart", "new", "lines")],
        [],
        {"scribe:gone": "already migrated"},
    )

    assert errors == [
        "Undeclared legacy snippet remains: quickstart:new",
        "Declared snippet blocker no longer exists: scribe:gone",
    ]
