from __future__ import annotations

import re

from .model import (
    ImmutableSourceReference,
    LocalSourceReference,
    PullRequestSourceReference,
)

IMMUTABLE_SOURCE_RE = re.compile(
    r"https://github\.com/(?P<repository>[^/]+/[^/]+)/blob/"
    r"(?P<commit>[0-9a-fA-F]{40})/(?P<path>[^?#]+)"
)
PULL_REQUEST_SOURCE_RE = re.compile(
    r"https://github\.com/(?P<repository>[^/]+/[^/]+)/pull/"
    r"(?P<pull_request>[1-9][0-9]*)"
)
LOCAL_SOURCE_RE = re.compile(
    r"local://(?P<repository>[^/]+/[^/]+)/(?P<path>[^?#]+)"
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


def parse_pull_request_source(
    value: str,
) -> PullRequestSourceReference | None:
    """Parse a canonical GitHub pull-request URL."""

    match = PULL_REQUEST_SOURCE_RE.fullmatch(value)
    if match is None:
        return None
    return PullRequestSourceReference(
        repository=match.group("repository"),
        pull_request=int(match.group("pull_request")),
    )


def parse_local_source(value: str) -> LocalSourceReference | None:
    """Parse a preview-only local repository reference."""

    match = LOCAL_SOURCE_RE.fullmatch(value)
    if match is None:
        return None
    return LocalSourceReference(
        repository=match.group("repository"),
        path=match.group("path"),
    )


def parse_source_reference(
    value: str,
) -> (
    ImmutableSourceReference
    | PullRequestSourceReference
    | LocalSourceReference
    | None
):
    """Classify a value as one of the supported snippet source forms."""

    return (
        parse_immutable_source(value)
        or parse_pull_request_source(value)
        or parse_local_source(value)
    )
