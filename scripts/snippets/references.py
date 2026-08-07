from __future__ import annotations

import re

from .model import ImmutableSourceReference

IMMUTABLE_SOURCE_RE = re.compile(
    r"https://github\.com/(?P<repository>[^/]+/[^/]+)/blob/"
    r"(?P<commit>[0-9a-fA-F]{40})/(?P<path>[^?#]+)"
)


def parse_immutable_source(value: str) -> ImmutableSourceReference | None:
    """Parse a full GitHub blob URL pinned to a 40-character commit."""

    match = IMMUTABLE_SOURCE_RE.fullmatch(value)
    if match is None:
        return None
    return ImmutableSourceReference(
        repository=match.group("repository"),
        commit=match.group("commit").lower(),
        path=match.group("path"),
    )
