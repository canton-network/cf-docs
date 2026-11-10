from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE = "docs-main/guide/example.mdx"
TEMPLATE = "docs-main/src/guide/example.mdx"


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "comment_generated_page_edits.py"
    scripts_dir = str(script_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[script_path.stem] = module
    spec.loader.exec_module(module)
    return module


def stale_report() -> dict[str, Any]:
    return {"stale": [{"page": PAGE, "template": TEMPLATE}], "orphans": [], "errors": []}


def test_regenerated_changes_are_not_hand_edits() -> None:
    module = load_script_module()
    base = "Intro\n\nOld sentence.\n"
    page_now = "{/* Generated from /src/guide/example.mdx */}\nIntro\n\nOld sentence.\n"
    expected = "{/* Generated from /src/guide/example.mdx */}\nIntro\n\nNew sentence from the template.\n"

    assert module.hand_edited_lines(base, page_now, expected) == []


def test_lines_missing_from_template_output_are_hand_edits_reported_once() -> None:
    module = load_script_module()
    base = "Intro\n\n<Tab title=\"DevNet\">\nShared\n</Tab>\n<Tab title=\"TestNet\">\nShared\n</Tab>\n"
    page_now = base.replace("Shared", "Typed into the page")
    expected = base

    assert module.hand_edited_lines(base, page_now, expected) == ["Typed into the page"]


def test_page_new_in_this_pull_request_is_not_a_hand_edit() -> None:
    module = load_script_module()

    assert module.hand_edited_lines(None, "Anything\n", "Something else\n") == []


def test_classify_and_comment_body_cover_every_problem_kind() -> None:
    module = load_script_module()
    report = {
        "stale": [
            {"page": PAGE, "template": TEMPLATE},
            {"page": "docs-main/other.mdx", "template": "docs-main/src/other.mdx"},
        ],
        "orphans": ["docs-main/orphan.mdx"],
        "errors": [{"template": "docs-main/src/broken.mdx", "message": "only tab"}],
    }

    problems = module.classify(report, {PAGE: ["Typed into the page"], "docs-main/other.mdx": []})
    body = module.comment_body(problems)

    assert [problem.kind for problem in problems] == ["template_error", "direct_edit", "regenerate", "orphan"]
    assert body.startswith(module.MARKER)
    assert f"`{PAGE}` was edited directly, but it is generated from `{TEMPLATE}`" in body
    assert "  ```text\n  Typed into the page\n  ```" in body
    assert "`docs-main/other.mdx` is out of date with `docs-main/src/other.mdx`" in body
    assert "`docs-main/orphan.mdx` is a generated page with no template" in body
    assert "`docs-main/src/broken.mdx` could not be rendered: only tab" in body
    assert "needs a local checkout" in body


def test_quoted_hand_edits_are_capped() -> None:
    module = load_script_module()
    lines = [f"Line {index}" for index in range(module.MAX_QUOTED_LINES + 2)]

    body = module.comment_body(module.classify(stale_report(), {PAGE: lines}))

    assert f"Line {module.MAX_QUOTED_LINES - 1}" in body
    assert f"Line {module.MAX_QUOTED_LINES}" not in body
    assert "… and 2 more" in body


class FakeGitHub:
    def __init__(self, comments: list[dict[str, Any]]) -> None:
        self.comments = comments
        self.writes: list[tuple[str, str, Any]] = []

    def request_json(self, url: str, *, user_agent: str, method: str = "GET", payload: Any = None) -> Any:
        if method == "GET":
            return self.comments
        self.writes.append((method, url, payload))
        return {}


@pytest.fixture
def fake_github(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, FakeGitHub]:
    module = load_script_module()
    fake = FakeGitHub([{"id": 1, "body": "Unrelated review comment"}])
    monkeypatch.setattr(module.github_api_utils, "request_json", fake.request_json)
    return module, fake


def test_upsert_posts_when_problems_and_no_marked_comment(fake_github: tuple[ModuleType, FakeGitHub]) -> None:
    module, fake = fake_github
    problems = module.classify(stale_report(), {})

    module.upsert_comment("owner/repo", 7, problems)

    assert fake.writes == [
        ("POST", "https://api.github.com/repos/owner/repo/issues/7/comments", {"body": module.comment_body(problems)})
    ]


def test_upsert_skips_when_clean_and_never_commented(fake_github: tuple[ModuleType, FakeGitHub]) -> None:
    module, fake = fake_github

    module.upsert_comment("owner/repo", 7, [])

    assert fake.writes == []


def test_upsert_marks_earlier_comment_resolved(fake_github: tuple[ModuleType, FakeGitHub]) -> None:
    module, fake = fake_github
    fake.comments.append({"id": 2, "body": f"{module.MARKER}\nold problems"})

    module.upsert_comment("owner/repo", 7, [])

    assert fake.writes == [
        ("PATCH", "https://api.github.com/repos/owner/repo/issues/comments/2", {"body": module.comment_body([])})
    ]


def test_upsert_leaves_current_comment_alone(fake_github: tuple[ModuleType, FakeGitHub]) -> None:
    module, fake = fake_github
    problems = module.classify(stale_report(), {})
    fake.comments.append({"id": 2, "body": module.comment_body(problems)})

    module.upsert_comment("owner/repo", 7, problems)

    assert fake.writes == []
