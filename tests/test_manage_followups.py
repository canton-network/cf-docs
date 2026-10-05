from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "manage_followups.py"
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


mf = load_script_module()

# 2026-09-01 is a Tuesday.
CREATED = datetime(2026, 9, 1, 9, tzinfo=UTC)


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 9, day, hour, tzinfo=UTC)


def team(day: int, *, feedback: bool = True, actor: str = "reviewer") -> object:
    return mf.Activity(actor=actor, at=at(day), is_team=True, is_feedback=feedback)


def by_author(day: int) -> object:
    return mf.Activity(actor="contrib", at=at(day), is_team=False, is_feedback=False)


@pytest.fixture
def config() -> object:
    return mf.Config.load(REPO_ROOT / ".github" / "followups.json")


def pr(**overrides: object) -> object:
    fields = {
        "kind": "pr",
        "number": 1,
        "author": "contrib",
        "title": "Fix <thing> & stuff",
        "url": "https://github.com/canton-network/cf-docs/pull/1",
        "created_at": CREATED,
        "labels": set(),
        "requested_reviewers": ["reviewer"],
        "activities": [by_author(1)],
    }
    fields.update(overrides)
    return mf.Item(**fields)


def issue(**overrides: object) -> object:
    fields = {
        "kind": "issue",
        "number": 2,
        "author": "contrib",
        "title": "Page is wrong",
        "url": "https://github.com/canton-network/cf-docs/issues/2",
        "created_at": CREATED,
        "labels": set(),
        "activities": [by_author(1)],
    }
    fields.update(overrides)
    return mf.Item(**fields)


def markers(plan: object) -> list[str]:
    return [comment.marker for comment in plan.comments]


def test_business_days_skip_weekends() -> None:
    # Friday 2026-09-04 to Monday 2026-09-07 is one business day.
    assert mf.business_days_between(at(4), at(7)) == 1
    assert mf.business_days_between(at(1), at(15)) == 10


def test_marker_round_trip() -> None:
    body = mf.stale_warning_body(pr(), mf.Config.load(REPO_ROOT / ".github" / "followups.json"))
    assert mf.parse_marker(body) == "stale-warning"
    assert mf.parse_marker("ordinary comment") is None


def test_pr_without_feedback_awaits_review(config) -> None:
    plan = mf.plan_open(pr(), config, at(2))
    assert plan.add_labels == {mf.LABEL_AWAITING_REVIEW}
    assert not plan.comments


def test_team_feedback_after_author_flips_to_awaiting_author(config) -> None:
    item = pr(labels={mf.LABEL_AWAITING_REVIEW}, activities=[by_author(1), team(2)])
    plan = mf.plan_open(item, config, at(3))
    assert plan.add_labels == {mf.LABEL_AWAITING_AUTHOR}
    assert plan.remove_labels == {mf.LABEL_AWAITING_REVIEW}


def test_approval_is_not_feedback(config) -> None:
    item = pr(activities=[by_author(1), team(2, feedback=False)])
    plan = mf.plan_open(item, config, at(3))
    assert plan.add_labels == {mf.LABEL_AWAITING_REVIEW}


def test_author_response_resets_to_awaiting_review(config) -> None:
    item = pr(labels={mf.LABEL_AWAITING_AUTHOR}, activities=[team(2), by_author(3)])
    plan = mf.plan_open(item, config, at(20))
    assert plan.add_labels == {mf.LABEL_AWAITING_REVIEW}
    assert plan.remove_labels == {mf.LABEL_AWAITING_AUTHOR}
    assert mf.MARKER_STALE_WARNING not in markers(plan)


def test_new_conflict_labels_and_comments_once(config) -> None:
    plan = mf.plan_open(pr(conflict=True), config, at(2))
    assert plan.add_labels == {mf.LABEL_MERGE_CONFLICT, mf.LABEL_AWAITING_AUTHOR}
    assert markers(plan) == [mf.MARKER_CONFLICT]
    assert "@contrib" in plan.comments[0].body

    notified = pr(
        conflict=True,
        labels={mf.LABEL_MERGE_CONFLICT, mf.LABEL_AWAITING_AUTHOR},
        markers=[mf.Marker(mf.MARKER_CONFLICT, at(2))],
    )
    assert mf.plan_open(notified, config, at(3)).is_empty()


def test_resolved_conflict_clears_label(config) -> None:
    item = pr(
        labels={mf.LABEL_MERGE_CONFLICT, mf.LABEL_AWAITING_AUTHOR},
        markers=[mf.Marker(mf.MARKER_CONFLICT, at(2))],
        activities=[by_author(1), by_author(3)],
    )
    plan = mf.plan_open(item, config, at(3, 13))
    assert plan.remove_labels == {mf.LABEL_MERGE_CONFLICT, mf.LABEL_AWAITING_AUTHOR}
    assert plan.add_labels == {mf.LABEL_AWAITING_REVIEW}


def test_unknown_mergeability_holds_nudges_and_closure(config) -> None:
    # The PR may conflict once GitHub finishes recomputing; don't nudge yet.
    waiting = mf.plan_open(pr(conflict=None), config, at(10))
    assert waiting.add_labels == {mf.LABEL_AWAITING_REVIEW}
    assert not waiting.comments
    assert not waiting.notifications

    stale = pr(
        conflict=None,
        activities=[by_author(1), team(2)],
        labels={mf.LABEL_AWAITING_AUTHOR},
        markers=[mf.Marker(mf.MARKER_STALE_WARNING, at(11))],
    )
    assert not mf.plan_open(stale, config, at(16)).close
    assert mf.plan_open(pr(**{**vars(stale), "conflict": False}), config, at(16)).close


def test_unknown_mergeability_keeps_existing_conflict_state(config) -> None:
    item = pr(
        conflict=None,
        labels={mf.LABEL_MERGE_CONFLICT, mf.LABEL_AWAITING_AUTHOR},
        markers=[mf.Marker(mf.MARKER_CONFLICT, at(2))],
    )
    assert mf.plan_open(item, config, at(3)).is_empty()


def test_stale_warning_then_close(config) -> None:
    feedback = [by_author(1), team(2)]
    # 7 business days after Wednesday 2026-09-02 is Friday 2026-09-11.
    assert not markers(mf.plan_open(pr(activities=feedback), config, at(10)))
    warn = mf.plan_open(pr(activities=feedback), config, at(11))
    assert markers(warn) == [mf.MARKER_STALE_WARNING]
    assert not warn.close

    warned = [mf.Marker(mf.MARKER_STALE_WARNING, at(11))]
    labels = {mf.LABEL_AWAITING_AUTHOR}
    early = mf.plan_open(pr(activities=feedback, markers=warned, labels=labels), config, at(15))
    assert early.is_empty()
    close = mf.plan_open(pr(activities=feedback, markers=warned, labels=labels), config, at(16))
    assert close.close
    assert markers(close) == [mf.MARKER_STALE_CLOSE]
    assert mf.LABEL_CLOSED_STALE in close.add_labels


def test_late_warning_still_gets_grace_period(config) -> None:
    item = pr(
        activities=[by_author(1), team(2)],
        labels={mf.LABEL_AWAITING_AUTHOR},
        markers=[mf.Marker(mf.MARKER_STALE_WARNING, at(21))],
    )
    assert not mf.plan_open(item, config, at(22)).close
    assert mf.plan_open(item, config, at(24)).close


FEEDBACK = [by_author(1), team(2)]
DOCS_TEAM_FEEDBACK = [
    mf.Activity("shreyas-da", at(1), is_team=True, is_feedback=False),
    team(2),
]


@pytest.mark.parametrize(
    "overrides",
    [
        {"draft": True, "activities": FEEDBACK},
        {"labels": {"on-hold"}, "activities": FEEDBACK},
        {"author": "shreyas-da", "activities": DOCS_TEAM_FEEDBACK},
        {"author": "richardkapolnai-da", "activities": FEEDBACK},
        {"author": "coldice", "activities": FEEDBACK},
        {"requested_reviewers": [], "conflict": True},
    ],
    ids=["draft", "exempt-label", "docs-team", "da-login", "allowlisted", "no-sme"],
)
def test_close_exemptions(config, overrides) -> None:
    plan = mf.plan_open(pr(**overrides), config, at(30))
    assert not plan.close
    assert mf.MARKER_STALE_WARNING not in markers(plan)


def test_unassigned_pr_alerts_docs_team_in_slack_once(config) -> None:
    # 7 business days after Tuesday 2026-09-01 is Thursday 2026-09-10.
    item = pr(requested_reviewers=[])
    assert mf.plan_open(item, config, at(9)).add_labels == {mf.LABEL_AWAITING_REVIEW}

    plan = mf.plan_open(item, config, at(10))
    assert plan.add_labels == {mf.LABEL_AWAITING_REVIEW, mf.LABEL_NEEDS_ASSIGNEE}
    assert plan.notifications == ["needs a reviewer, waiting 7 business days"]
    assert not plan.comments

    alerted = pr(
        requested_reviewers=[],
        labels={mf.LABEL_AWAITING_REVIEW, mf.LABEL_NEEDS_ASSIGNEE},
    )
    assert mf.plan_open(alerted, config, at(20)).is_empty()


def test_assigning_reviewer_clears_needs_assignee(config) -> None:
    item = pr(labels={mf.LABEL_AWAITING_REVIEW, mf.LABEL_NEEDS_ASSIGNEE})
    plan = mf.plan_open(item, config, at(2))
    assert plan.remove_labels == {mf.LABEL_NEEDS_ASSIGNEE}
    assert not plan.notifications


def test_awaiting_author_clears_needs_assignee(config) -> None:
    item = pr(
        requested_reviewers=[],
        conflict=True,
        labels={mf.LABEL_AWAITING_REVIEW, mf.LABEL_NEEDS_ASSIGNEE, mf.LABEL_MERGE_CONFLICT},
        markers=[mf.Marker(mf.MARKER_CONFLICT, at(2))],
    )
    plan = mf.plan_open(item, config, at(3))
    assert mf.LABEL_NEEDS_ASSIGNEE in plan.remove_labels
    assert not plan.notifications


def test_draft_clears_needs_assignee(config) -> None:
    item = pr(draft=True, labels={mf.LABEL_AWAITING_REVIEW, mf.LABEL_NEEDS_ASSIGNEE})
    plan = mf.plan_open(item, config, at(20))
    assert plan.remove_labels == {mf.LABEL_AWAITING_REVIEW, mf.LABEL_NEEDS_ASSIGNEE}
    assert not plan.notifications


def test_assigned_reviewer_delay_nudges_on_github_and_slack(config) -> None:
    assert not markers(mf.plan_open(pr(), config, at(9)))
    plan = mf.plan_open(pr(), config, at(10))
    assert markers(plan) == [mf.MARKER_REVIEWER_NUDGE]
    body = plan.comments[0].body
    assert "@contrib" in body
    assert "@reviewer" in body
    assert plan.notifications == [
        "nudged author and reviewer, waiting on review 7 business days"
    ]
    assert mf.LABEL_NEEDS_ASSIGNEE not in plan.add_labels

    nudged = pr(markers=[mf.Marker(mf.MARKER_REVIEWER_NUDGE, at(10))])
    later = mf.plan_open(nudged, config, at(20))
    assert not markers(later)
    assert not later.notifications


def test_author_reply_in_review_thread_hands_back_to_reviewer(config) -> None:
    # Regression for cf-docs#1148: the author answered inside the review thread,
    # which the issue timeline does not show.
    review = mf.Activity("thibault-da", at(10, 14), is_team=True, is_feedback=True, is_review=True)
    reply = mf.pull_activities(
        [],
        [
            {
                "user": {"login": "contrib", "type": "User"},
                "author_association": "CONTRIBUTOR",
                "created_at": "2026-09-10T15:18:28Z",
            }
        ],
        "contrib",
    )
    item = pr(requested_reviewers=[], activities=[by_author(1), review, *reply])
    plan = mf.plan_open(item, config, at(21))
    assert plan.add_labels == {mf.LABEL_AWAITING_REVIEW}
    assert markers(plan) == [mf.MARKER_REVIEWER_NUDGE]
    assert "@thibault-da" in plan.comments[0].body


def test_pull_activities_attribute_commits_to_their_authors() -> None:
    commits = [
        {"author": {"login": "shreyas-da"}, "commit": {"committer": {"date": "2026-09-10T09:37:35Z"}}},
        {"author": None, "commit": {"committer": {"date": "2026-09-11T09:00:00Z"}}},
    ]
    bot_comment = {"user": {"login": "x[bot]", "type": "Bot"}, "created_at": "2026-09-12T00:00:00Z"}
    activities = mf.pull_activities(commits, [bot_comment], "contrib")
    assert [(a.actor, a.is_feedback) for a in activities] == [
        ("shreyas-da", False),
        ("contrib", False),
    ]


def test_issue_team_feedback_awaits_author_automatically(config) -> None:
    item = issue(activities=[by_author(1), team(2)])
    assert mf.plan_open(item, config, at(3)).add_labels == {mf.LABEL_AWAITING_AUTHOR}

    labeled = issue(activities=[by_author(1), team(2)], labels={mf.LABEL_AWAITING_AUTHOR})
    assert markers(mf.plan_open(labeled, config, at(11))) == [mf.MARKER_STALE_WARNING]

    answered = issue(activities=[team(2), by_author(3)], labels={mf.LABEL_AWAITING_AUTHOR})
    assert mf.plan_open(answered, config, at(4)).add_labels == {mf.LABEL_AWAITING_REVIEW}


def test_issue_manual_label_awaits_author(config) -> None:
    # No team comment: the label alone hands the issue to its author.
    labeled = issue(
        activities=[by_author(1)],
        labels={mf.LABEL_AWAITING_AUTHOR},
        awaiting_author_labeled_at=at(2),
    )
    plan = mf.plan_open(labeled, config, at(11))
    assert markers(plan) == [mf.MARKER_STALE_WARNING]


def test_unassigned_issue_alerts_docs_team(config) -> None:
    plan = mf.plan_open(issue(), config, at(10))
    assert mf.LABEL_NEEDS_ASSIGNEE in plan.add_labels
    assert plan.notifications == ["needs an assignee, waiting 7 business days"]
    assert not plan.comments

    assigned = mf.plan_open(issue(assignees=["someone"]), config, at(10))
    assert mf.LABEL_NEEDS_ASSIGNEE not in assigned.add_labels
    assert not assigned.notifications


def test_author_comment_reopens_stale_closed_item(config) -> None:
    closed = pr(
        labels={mf.LABEL_CLOSED_STALE, mf.LABEL_AWAITING_AUTHOR},
        closed_at=at(16),
        activities=[by_author(1), team(2)],
    )
    assert mf.plan_closed(closed, config, at(17)).is_empty()

    closed.activities.append(by_author(18))
    plan = mf.plan_closed(closed, config, at(19))
    assert plan.reopen
    assert plan.remove_labels == {mf.LABEL_CLOSED_STALE, mf.LABEL_AWAITING_AUTHOR}
    assert plan.add_labels == {mf.LABEL_AWAITING_REVIEW}


def test_timeline_parsing_skips_bots_and_records_markers() -> None:
    events = [
        {
            "event": "commented",
            "user": {"login": "github-actions[bot]", "type": "Bot"},
            "body": "<!-- cf-docs-followups:conflict -->\nhi",
            "created_at": "2026-09-02T00:00:00Z",
        },
        {
            "event": "commented",
            "user": {"login": "dependabot[bot]", "type": "Bot"},
            "body": "bump",
            "created_at": "2026-09-02T00:00:00Z",
        },
        {
            "event": "reviewed",
            "user": {"login": "reviewer", "type": "User"},
            "author_association": "MEMBER",
            "state": "approved",
            "submitted_at": "2026-09-03T00:00:00Z",
        },
        {
            "event": "labeled",
            "actor": {"login": "reviewer", "type": "User"},
            "label": {"name": mf.LABEL_AWAITING_AUTHOR},
            "created_at": "2026-09-05T00:00:00Z",
        },
    ]
    activities, found_markers, labeled_at = mf.timeline_activities(events, "contrib")
    assert [m.name for m in found_markers] == ["conflict"]
    assert [(a.actor, a.is_team, a.is_feedback, a.is_review) for a in activities] == [
        ("reviewer", True, False, True),
    ]
    assert labeled_at == datetime(2026, 9, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Please rename this section.", True),
        ("@contrib can you rebase?", True),
        ("@thibault-da any update on this?", False),
        ("cc @canton-network/docs", False),
        ("@thibault-da @contrib thoughts?", True),
        ("mail me at someone@example.com", True),
    ],
)
def test_addresses_author(body, expected) -> None:
    assert mf.addresses_author(body, "contrib") is expected


def test_team_comment_pinging_reviewer_keeps_pr_awaiting_review(config) -> None:
    # Regression for cf-docs#1148: "@thibault-da any update on this?" from the
    # docs team must not hand the PR back to its author.
    events = [
        {
            "event": "commented",
            "user": {"login": "shreyas-da", "type": "User"},
            "author_association": "MEMBER",
            "body": "@thibault-da any update on this?",
            "created_at": "2026-10-01T16:34:32Z",
        }
    ]
    activities, _, _ = mf.timeline_activities(events, "contrib")
    item = pr(activities=[by_author(10), *activities])
    assert mf.plan_open(item, config, datetime(2026, 10, 1, 17, tzinfo=UTC)).add_labels == {
        mf.LABEL_AWAITING_REVIEW
    }


def test_employee_logins(config) -> None:
    assert mf.is_employee_login("JoaoSa-DA", config)
    assert mf.is_employee_login("jatinp26", config)
    # DA-style names without the -da suffix need an explicit allowlist entry.
    assert mf.is_employee_login("mziolekda", config)
    assert not mf.is_employee_login("angelol", config)
    assert not mf.is_employee_login("someoneda", config)


def test_team_member_uses_login_rule_when_association_is_hidden(config) -> None:
    # The Actions token sees private org members as CONTRIBUTOR.
    assert mf.is_team_member("thibault-da", "CONTRIBUTOR", config)
    assert mf.is_team_member("coldice", "CONTRIBUTOR", config)
    assert mf.is_team_member("8bitpal", "COLLABORATOR", config)
    assert not mf.is_team_member("angelol", "NONE", config)


def test_slack_payload_links_and_escapes_items() -> None:
    payload = mf.slack_payload(
        "canton-network/cf-docs",
        [
            (pr(), "needs a reviewer, waiting 7 business days"),
            (issue(author="a<b"), "needs an assignee, waiting 9 business days"),
        ],
        ("U1", "U2"),
    )
    assert payload == {
        "text": "\n".join(
            [
                "*Docs follow-ups for canton-network/cf-docs* <@U1> <@U2>",
                "• <https://github.com/canton-network/cf-docs/pull/1|PR #1: Fix &lt;thing&gt; &amp; stuff>"
                " (@contrib): needs a reviewer, waiting 7 business days",
                "• <https://github.com/canton-network/cf-docs/issues/2|Issue #2: Page is wrong>"
                " (@a&lt;b): needs an assignee, waiting 9 business days",
            ]
        )
    }


class FakeGitHub:
    """Serves one open unassigned PR and records writes."""

    repo = "canton-network/cf-docs"

    def __init__(self, reviewers: list[str] | None = None) -> None:
        self.writes: list[tuple[str, str]] = []
        self.reviewers = reviewers or []

    def ensure_labels(self) -> None:
        pass

    def paginate(self, path: str, params: dict | None = None) -> list:
        if path == "/issues":
            if (params or {}).get("state") == "closed":
                return []
            return [
                {
                    "number": 1,
                    "title": "Fix it",
                    "html_url": "https://github.com/canton-network/cf-docs/pull/1",
                    "user": {"login": "contrib"},
                    "created_at": "2026-09-01T09:00:00Z",
                    "labels": [],
                    "assignees": [],
                    "pull_request": {},
                }
            ]
        return []

    def get(self, path: str, params: dict | None = None) -> dict:
        assert path == "/pulls/1"
        return {
            "draft": False,
            "requested_reviewers": [{"login": name} for name in self.reviewers],
            "mergeable": True,
            "mergeable_state": "clean",
        }

    def write(self, method: str, path: str, payload: object = None) -> None:
        self.writes.append((method, path))


def test_run_writes_slack_payload_only_when_alerts_exist(config, tmp_path) -> None:
    github = FakeGitHub()
    slack = tmp_path / "slack.json"

    assert mf.run(github, config, at(3), slack_path=slack) == 0
    assert not slack.exists()

    assert mf.run(github, config, at(10), slack_path=slack) == 0
    payload = json.loads(slack.read_text())
    assert "PR #1: Fix it" in payload["text"]
    assert "needs a reviewer" in payload["text"]
    assert ("POST", "/issues/1/labels") in github.writes


def test_manual_reviewer_nudge_suppresses_bot_nudge(config) -> None:
    # One-off for cf-docs#1148: a human already chased the reviewer.
    assert config.manual_reviewer_nudges[1148] == datetime(2026, 10, 1, 16, 34, 32, tzinfo=UTC)

    github = FakeGitHub(reviewers=["reviewer"])
    assert mf.run(github, config, at(10)) == 0
    assert ("POST", "/issues/1/comments") in github.writes

    suppressed = mf.Config(**{**vars(config), "manual_reviewer_nudges": {1: at(9)}})
    github = FakeGitHub(reviewers=["reviewer"])
    assert mf.run(github, suppressed, at(10)) == 0
    assert ("POST", "/issues/1/comments") not in github.writes
