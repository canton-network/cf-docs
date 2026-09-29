from __future__ import annotations

import re


PRERELEASE_RANK = {
    "snapshot": 0,
    "alpha": 1,
    "beta": 2,
    "rc": 3,
}


def _version_parts(
    version: str,
) -> tuple[tuple[int, ...], tuple[int, tuple[tuple[int, int | str], ...]]]:
    normalized = version.strip().removeprefix("v").split("+", 1)[0]
    release_text, separator, prerelease_text = normalized.partition("-")
    release_tokens = re.split(r"[._]", release_text)
    release: list[int] = []
    for token in release_tokens:
        if not token.isdigit():
            raise ValueError(f"Version is not comparable: {version}")
        release.append(int(token))
    while len(release) < 3:
        release.append(0)

    if not separator:
        return tuple(release), (5, ())

    prerelease_tokens = [
        token for token in re.split(r"[._-]", prerelease_text) if token
    ]
    label = prerelease_tokens[0].lower() if prerelease_tokens else ""
    label_match = re.fullmatch(r"([a-z]+)(\d+)", label)
    if label_match:
        prerelease_tokens = [
            label_match.group(1),
            label_match.group(2),
            *prerelease_tokens[1:],
        ]
        label = prerelease_tokens[0]
    rank = PRERELEASE_RANK.get(label, 4)
    comparable_tokens: list[tuple[int, int | str]] = []
    for token in prerelease_tokens[1:]:
        comparable_tokens.append(
            (0, int(token)) if token.isdigit() else (1, token.lower())
        )
    return tuple(release), (rank, tuple(comparable_tokens))


def compare_versions(
    left: str,
    right: str,
    *,
    known_order: tuple[str, ...] = (),
) -> int:
    if left == right:
        return 0
    known_indexes = {version: index for index, version in enumerate(known_order)}
    if left in known_indexes and right in known_indexes:
        return -1 if known_indexes[left] < known_indexes[right] else 1

    left_parts = _version_parts(left)
    right_parts = _version_parts(right)
    if left_parts < right_parts:
        return -1
    if left_parts > right_parts:
        return 1
    return -1 if left < right else 1
