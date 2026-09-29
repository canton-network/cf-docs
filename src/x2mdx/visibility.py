"""Version-scoped visibility for authored development-only APIs."""

from collections.abc import Iterable, Mapping


def dev_only_identities(observations: Iterable[Mapping[str, str | None]]) -> set[str]:
    """Hide identities whose last present observation is dev (oldest first)."""
    latest: dict[str, str | None] = {}
    for states in observations:
        latest.update(states)
    return {identity for identity, state in latest.items() if state == "dev"}
