from __future__ import annotations

import difflib
from pathlib import Path

from x2mdx.cli import main as cli_main

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "expected"


def run_x2mdx(args: list[str]) -> None:
    result = cli_main(args)
    if result != 0:
        raise AssertionError(f"x2mdx exited with {result}: {args}")


def mdx_file_set(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*.mdx")}


def read_mdx(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def text_file_tree(root: Path, *, suffixes: tuple[str, ...] = (".mdx", ".json")) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix in suffixes
    }


def assert_text_tree_matches_fixture(actual_root: Path, fixture_name: str) -> None:
    expected_root = FIXTURE_ROOT / fixture_name
    actual = text_file_tree(actual_root)
    expected = text_file_tree(expected_root)
    if actual != expected:
        shared_files = sorted(set(actual) & set(expected))
        first_diff = ""
        for path in shared_files:
            if actual[path] == expected[path]:
                continue
            first_diff = "\n".join(
                difflib.unified_diff(
                    expected[path].splitlines(),
                    actual[path].splitlines(),
                    fromfile=f"expected/{fixture_name}/{path}",
                    tofile=f"actual/{path}",
                    lineterm="",
                    n=3,
                )
            )
            break
        raise AssertionError(
            f"Generated text tree did not match fixture {fixture_name!r}.\n"
            f"Actual files: {sorted(actual)}\n"
            f"Expected files: {sorted(expected)}"
            + (f"\nFirst content diff:\n{first_diff}" if first_diff else "")
        )


def assert_text_file_matches_fixture(actual_file: Path, fixture_name: str) -> None:
    expected_file = FIXTURE_ROOT / fixture_name
    actual = actual_file.read_text(encoding="utf-8")
    expected = expected_file.read_text(encoding="utf-8")
    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile=f"expected/{fixture_name}",
                tofile=str(actual_file),
                lineterm="",
                n=3,
            )
        )
        raise AssertionError(f"Generated text file did not match fixture {fixture_name!r}\n{diff}")


def assert_contains_all(text: str, fragments: list[str]) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    if missing:
        raise AssertionError(f"Missing fragments: {missing}")


def assert_contains_none(text: str, fragments: list[str]) -> None:
    present = [fragment for fragment in fragments if fragment in text]
    if present:
        raise AssertionError(f"Unexpected fragments: {present}")
