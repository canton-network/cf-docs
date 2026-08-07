from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .migrate_legacy import (
    CONFIG_ROOT,
    LegacyMigrationError,
    LegacySnippet,
    load_legacy_snippets,
)

DEFAULT_BLOCKERS = CONFIG_ROOT / "legacy-inline-blockers.json"


@dataclass(frozen=True)
class BlockerGroup:
    source_repo: str
    location_type: str
    transform: str | None
    count: int
    reason: str

    def matches(self, snippet: LegacySnippet) -> bool:
        return (
            snippet.alias == self.source_repo
            and snippet.location.get("type") == self.location_type
            and snippet.options.get("transform") == self.transform
        )


def _nonempty_string(raw: Any, *, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise LegacyMigrationError(f"Blocker {field} must be a non-empty string")
    return raw


def load_blockers(path: Path) -> tuple[list[BlockerGroup], dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_groups = payload.get("groups")
    raw_snippets = payload.get("snippets")
    if not isinstance(raw_groups, list) or not isinstance(raw_snippets, dict):
        raise LegacyMigrationError(f"Invalid blocker inventory {path}")
    groups: list[BlockerGroup] = []
    for raw in raw_groups:
        if not isinstance(raw, dict):
            raise LegacyMigrationError(f"Invalid blocker group in {path}")
        count = raw.get("count")
        transform = raw.get("transform")
        if not isinstance(count, int) or count < 1:
            raise LegacyMigrationError("Blocker group count must be a positive integer")
        if transform is not None and not isinstance(transform, str):
            raise LegacyMigrationError(
                "Blocker group transform must be a string or null"
            )
        groups.append(
            BlockerGroup(
                source_repo=_nonempty_string(raw.get("sourceRepo"), field="sourceRepo"),
                location_type=_nonempty_string(
                    raw.get("locationType"), field="locationType"
                ),
                transform=transform,
                count=count,
                reason=_nonempty_string(raw.get("reason"), field="reason"),
            )
        )
    snippets = {
        _nonempty_string(key, field="snippet key"): _nonempty_string(
            reason, field=f"reason for {key}"
        )
        for key, reason in raw_snippets.items()
    }
    return groups, snippets


def verify_blockers(
    legacy_snippets: list[LegacySnippet],
    groups: list[BlockerGroup],
    declared_snippets: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    matched_explicit: set[str] = set()
    group_counts = [0] * len(groups)
    for snippet in legacy_snippets:
        key = f"{snippet.alias}:{snippet.name}"
        matching_groups = [
            index for index, group in enumerate(groups) if group.matches(snippet)
        ]
        if key in declared_snippets:
            matched_explicit.add(key)
        elif len(matching_groups) == 1:
            group_counts[matching_groups[0]] += 1
        elif not matching_groups:
            errors.append(f"Undeclared legacy snippet remains: {key}")
        else:
            errors.append(f"Legacy snippet matches multiple blocker groups: {key}")
    for missing in sorted(set(declared_snippets) - matched_explicit):
        errors.append(f"Declared snippet blocker no longer exists: {missing}")
    for group, actual in zip(groups, group_counts, strict=True):
        if actual != group.count:
            errors.append(
                f"Blocker group {group.source_repo}/{group.location_type}/{group.transform} "
                f"expected {group.count} snippet(s), found {actual}"
            )
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that every remaining legacy snippet has a declared blocker"
    )
    parser.add_argument("--blockers", type=Path, default=DEFAULT_BLOCKERS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        groups, declared = load_blockers(args.blockers)
        snippets = load_legacy_snippets()
        errors = verify_blockers(snippets, groups, declared)
    except (LegacyMigrationError, OSError, ValueError) as exception:
        print(exception, file=sys.stderr)
        return 1
    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        return 1
    print(
        f"Verified {len(snippets)} remaining legacy snippet(s): "
        f"{len(groups)} grouped blocker(s), {len(declared)} explicit blocker(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
