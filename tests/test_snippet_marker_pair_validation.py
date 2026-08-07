from __future__ import annotations

import pytest

from scripts.snippets.validation import has_valid_marker_pair


@pytest.mark.parametrize(
    ("start_after", "end_before"),
    [
        (None, None),
        ("SWEEP_START", "SWEEP_END"),
        ("<!-- start -->", "<!-- end -->"),
    ],
)
def test_accepts_absent_or_complete_distinct_markers(
    start_after: str | None, end_before: str | None
) -> None:
    assert has_valid_marker_pair(start_after, end_before)


@pytest.mark.parametrize(
    ("start_after", "end_before"),
    [
        ("START", None),
        (None, "END"),
        ("", "END"),
        ("START", ""),
        ("SAME", "SAME"),
        (1, "END"),
        ("START", 2),
    ],
)
def test_rejects_partial_empty_equal_or_nonstring_markers(
    start_after: str | int | None, end_before: str | int | None
) -> None:
    assert not has_valid_marker_pair(start_after, end_before)
