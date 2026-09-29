from __future__ import annotations

import importlib.util
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
        {"requested_reviewers": [], "conflict": True},
    ],
    ids=["draft", "exempt-label", "docs-team", "no-sme"],
)
def test_close_exemptions(config, overrides) -> None:
    plan = mf.plan_open(pr(**overrides), config, at(30))
    assert not plan.close
    assert mf.MARKER_STALE_WARNING not in markers(plan)


def test_review_reminder_for_unassigned_pr(config) -> None:
    item = pr(requested_reviewers=[])
    assert not markers(mf.plan_open(item, config, at(7)))
    plan = mf.plan_open(item, config, at(8, 13))
    assert markers(plan) == [mf.MARKER_REVIEW_REMINDER]
    assert config.reviewer_ping in plan.comments[0].body

    reminded = pr(requested_reviewers=[], markers=[mf.Marker(mf.MARKER_REVIEW_REMINDER, at(8))])
    assert not markers(mf.plan_open(reminded, config, at(20)))


def test_no_review_reminder_when_reviewer_assigned(config) -> None:
    assert not markers(mf.plan_open(pr(), config, at(20)))


def test_issue_awaits_author_only_when_labeled(config) -> None:
    unlabeled = issue(activities=[by_author(1), team(2)])
    assert mf.plan_open(unlabeled, config, at(3)).add_labels == {mf.LABEL_AWAITING_REVIEW}

    labeled = issue(
        activities=[by_author(1), team(2)],
        labels={mf.LABEL_AWAITING_AUTHOR},
        awaiting_author_labeled_at=at(2),
    )
    plan = mf.plan_open(labeled, config, at(11))
    assert markers(plan) == [mf.MARKER_STALE_WARNING]


def test_issue_triage_reminder_skips_assigned(config) -> None:
    assert markers(mf.plan_open(issue(), config, at(10))) == [mf.MARKER_REVIEW_REMINDER]
    assert not markers(mf.plan_open(issue(assignees=["someone"]), config, at(10)))


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
            "event": "committed",
            "committer": {"date": "2026-09-04T00:00:00Z"},
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
    assert [(a.actor, a.is_team, a.is_feedback) for a in activities] == [
        ("reviewer", True, False),
        ("contrib", False, False),
    ]
    assert labeled_at == datetime(2026, 9, 5, tzinfo=UTC)
