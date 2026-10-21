#!/usr/bin/env python3
"""Explain stale generated pages on a pull request with one updatable comment."""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

import generate_network_variable_tabs as generator
import github_api_utils

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = "https://api.github.com"
USER_AGENT = "cf-docs-generated-page-edits"
MARKER = "<!-- cf-docs-generated-page-edits -->"
GENERATE_COMMAND = "npm run generate:network-variable-tabs"
MAX_QUOTED_LINES = 5


class StaleEntry(TypedDict):
    page: str
    template: str


class TemplateError(TypedDict):
    template: str
    message: str


class IssueComment(TypedDict):
    id: int
    body: str | None


class Report(TypedDict):
    stale: list[StaleEntry]
    orphans: list[str]
    errors: list[TemplateError]


@dataclass(frozen=True)
class Problem:
    kind: Literal["direct_edit", "regenerate", "orphan", "template_error"]
    page: str | None
    template: str | None
    message: str | None = None
    hand_edited: tuple[str, ...] = ()


def hand_edited_lines(page_at_base: str | None, page_now: str, expected: str) -> list[str]:
    """Lines this PR added to a generated page that its template does not produce."""
    if page_at_base is None:
        return []
    produced = {line.strip() for line in expected.splitlines()}
    diff = difflib.unified_diff(page_at_base.splitlines(), page_now.splitlines(), lineterm="", n=0)
    added = (line[1:] for line in diff if line.startswith("+") and not line.startswith("+++"))
    # A line inside network tabs repeats once per network; report it once.
    return list(dict.fromkeys(line for line in added if line.strip() and line.strip() not in produced))


def classify(report: Report, hand_edits: dict[str, list[str]]) -> list[Problem]:
    problems = [
        Problem(kind="template_error", page=None, template=error["template"], message=error["message"])
        for error in report["errors"]
    ]
    for entry in report["stale"]:
        lines = tuple(hand_edits.get(entry["page"], ()))
        problems.append(
            Problem(
                kind="direct_edit" if lines else "regenerate",
                page=entry["page"],
                template=entry["template"],
                hand_edited=lines,
            )
        )
    problems.extend(Problem(kind="orphan", page=page, template=None) for page in report["orphans"])
    return problems


def describe(problem: Problem) -> str:
    if problem.kind == "direct_edit":
        quoted = [f"  {line}" for line in problem.hand_edited[:MAX_QUOTED_LINES]]
        if len(problem.hand_edited) > MAX_QUOTED_LINES:
            quoted.append(f"  … and {len(problem.hand_edited) - MAX_QUOTED_LINES} more")
        return "\n".join(
            [
                f"- `{problem.page}` was edited directly, but it is generated from `{problem.template}`. "
                "Make the change in the template (in the Mintlify editor it is under **Page templates**), "
                f"then run `{GENERATE_COMMAND}`. Edits made only to the generated page are overwritten. "
                "Lines found only in the generated page:",
                "",
                "  ```text",
                *quoted,
                "  ```",
            ]
        )
    if problem.kind == "regenerate":
        return (
            f"- `{problem.page}` is out of date with `{problem.template}`. "
            f"Run `{GENERATE_COMMAND}` and commit the result."
        )
    if problem.kind == "orphan":
        return (
            f"- `{problem.page}` is a generated page with no template under `docs-main/src/`. "
            "Restore the template or delete the page."
        )
    return f"- `{problem.template}` could not be rendered: {problem.message}"


def comment_body(problems: list[Problem]) -> str:
    if not problems:
        return (
            f"{MARKER}\n"
            "**Generated pages are up to date.** The issues reported earlier on this pull request are resolved."
        )
    lines = [
        MARKER,
        "**Generated pages need attention.** Pages with network tabs are generated from templates "
        "under `docs-main/src/`; edit the template, not the generated page.",
        "",
        *(describe(problem) for problem in problems),
    ]
    if any(problem.kind in {"direct_edit", "regenerate"} for problem in problems):
        lines.extend(
            [
                "",
                f"`{GENERATE_COMMAND}` needs a local checkout. If you edited in the Mintlify editor, "
                "ask someone with one to regenerate this branch.",
            ]
        )
    return "\n".join(lines)


def file_at(commit: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def collect_hand_edits(report: Report, base: str) -> dict[str, list[str]]:
    if not report["stale"]:
        return {}
    network_data = generator.load_network_data()
    hand_edits: dict[str, list[str]] = {}
    for entry in report["stale"]:
        expected = generator.render_page(REPO_ROOT / entry["template"], network_data)
        page_now = (REPO_ROOT / entry["page"]).read_text(encoding="utf-8")
        hand_edits[entry["page"]] = hand_edited_lines(file_at(base, entry["page"]), page_now, expected)
    return hand_edits


def load_report(path: Path) -> Report:
    return json.loads(path.read_text(encoding="utf-8"))


def find_marked_comment(repo: str, pr: int) -> IssueComment | None:
    page = 1
    while True:
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        comments: list[IssueComment] = github_api_utils.request_json(
            f"{API_ROOT}/repos/{repo}/issues/{pr}/comments?{query}", user_agent=USER_AGENT
        )
        for comment in comments:
            if MARKER in (comment["body"] or ""):
                return comment
        if len(comments) < 100:
            return None
        page += 1


def upsert_comment(repo: str, pr: int, problems: list[Problem]) -> str:
    existing = find_marked_comment(repo, pr)
    if not problems and existing is None:
        return "No generated-page problems and no earlier comment; nothing to post."
    body = comment_body(problems)
    if existing is not None:
        if existing["body"] == body:
            return "Generated-page comment is already current."
        github_api_utils.request_json(
            f"{API_ROOT}/repos/{repo}/issues/comments/{existing['id']}",
            user_agent=USER_AGENT,
            method="PATCH",
            payload={"body": body},
        )
        return "Updated the generated-page comment."
    github_api_utils.request_json(
        f"{API_ROOT}/repos/{repo}/issues/{pr}/comments",
        user_agent=USER_AGENT,
        method="POST",
        payload={"body": body},
    )
    return "Posted a generated-page comment."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="JSON report from generate_network_variable_tabs.py.")
    parser.add_argument("--base", required=True, help="Base commit of the pull request.")
    parser.add_argument("--repo", help="owner/name of the repository.")
    parser.add_argument("--pr", type=int, help="Pull request number.")
    parser.add_argument("--dry-run", action="store_true", help="Print the comment instead of posting it.")
    args = parser.parse_args()

    if not args.report.exists():
        print(f"No report at {args.report}; the generator did not run, so there is nothing to explain.")
        return
    report = load_report(args.report)
    problems = classify(report, collect_hand_edits(report, args.base))
    if args.dry_run:
        print(comment_body(problems))
        return
    if not args.repo or not args.pr:
        parser.error("--repo and --pr are required unless --dry-run is set")
    print(upsert_comment(args.repo, args.pr, problems))


if __name__ == "__main__":
    main()
