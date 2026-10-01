#!/usr/bin/env python3
"""Label, nudge, and close stale pull requests and issues.

Implements the follow-up policy from canton-network/cf-docs#1693:

- PRs that conflict with the base branch get a label and an explanatory comment.
- Open PRs and issues carry exactly one of `status/awaiting-author` or
  `status/awaiting-review`.
- Items awaiting the author get a warning after `warn_business_days` and are
  closed after `close_business_days`. Author activity resets the clock, and an
  author comment on an item closed this way reopens it.
- Items awaiting review with nobody assigned get `status/needs-assignee` and
  one Slack alert to the docs team. PRs whose assigned reviewer has not
  responded get one GitHub nudge tagging the author and the reviewers, and the
  docs team hears about it in Slack.

The script is dry-run by default; pass `--apply` to write to GitHub. With
`--slack-payload PATH`, Slack alerts are written to PATH as an incoming-webhook
payload for the workflow to send.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import github_api_utils

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / ".github" / "followups.json"
USER_AGENT = "cf-docs-followups"
API_ROOT = "https://api.github.com"

LABEL_AWAITING_AUTHOR = "status/awaiting-author"
LABEL_AWAITING_REVIEW = "status/awaiting-review"
LABEL_MERGE_CONFLICT = "status/merge-conflict"
LABEL_CLOSED_STALE = "status/closed-stale"
LABEL_NEEDS_ASSIGNEE = "status/needs-assignee"
STATUS_LABELS = {
    LABEL_AWAITING_AUTHOR: ("d93f0b", "Waiting on the contributor"),
    LABEL_AWAITING_REVIEW: ("0e8a16", "Waiting on the docs team"),
    LABEL_MERGE_CONFLICT: ("b60205", "Conflicts with the base branch"),
    LABEL_CLOSED_STALE: ("cccccc", "Closed after no author response"),
    LABEL_NEEDS_ASSIGNEE: ("fbca04", "Docs team needs to assign a reviewer"),
}

MARKER_PREFIX = "<!-- cf-docs-followups:"
MARKER_CONFLICT = "conflict"
MARKER_STALE_WARNING = "stale-warning"
MARKER_STALE_CLOSE = "stale-close"
MARKER_REVIEWER_NUDGE = "reviewer-nudge"
MARKER_REOPENED = "reopened"

TEAM_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
MENTION_PATTERN = re.compile(r"(?<![\w@])@([A-Za-z0-9-]+(?:/[A-Za-z0-9_.-]+)?)")

ItemKind = Literal["pr", "issue"]


@dataclass(frozen=True)
class Config:
    docs_team: frozenset[str]
    exempt_labels: frozenset[str]
    warn_business_days: int
    close_business_days: int
    review_reminder_business_days: int
    reviewer_nudge_business_days: int
    reopen_window_days: int

    @classmethod
    def load(cls, path: Path) -> Config:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            docs_team=frozenset(login.lower() for login in raw["docs_team"]),
            exempt_labels=frozenset(raw["exempt_labels"]),
            warn_business_days=raw["warn_business_days"],
            close_business_days=raw["close_business_days"],
            review_reminder_business_days=raw["review_reminder_business_days"],
            reviewer_nudge_business_days=raw["reviewer_nudge_business_days"],
            reopen_window_days=raw["reopen_window_days"],
        )


@dataclass(frozen=True)
class Activity:
    """A human action on an item, used to decide whose turn it is."""

    actor: str
    at: datetime
    is_team: bool
    # True when the action asks the author for something: a comment or a
    # non-approving review. Approvals and pushes are not feedback.
    is_feedback: bool
    is_review: bool = False


@dataclass(frozen=True)
class Marker:
    name: str
    at: datetime


@dataclass
class Item:
    kind: ItemKind
    number: int
    author: str
    title: str
    url: str
    created_at: datetime
    labels: set[str]
    draft: bool = False
    assignees: list[str] = field(default_factory=list)
    requested_reviewers: list[str] = field(default_factory=list)
    # None means GitHub has not finished computing mergeability.
    conflict: bool | None = False
    activities: list[Activity] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    # When a team member last applied `status/awaiting-author` (issues only).
    awaiting_author_labeled_at: datetime | None = None
    closed_at: datetime | None = None


@dataclass(frozen=True)
class Comment:
    marker: str
    body: str


@dataclass
class Plan:
    add_labels: set[str] = field(default_factory=set)
    remove_labels: set[str] = field(default_factory=set)
    comments: list[Comment] = field(default_factory=list)
    close: bool = False
    reopen: bool = False
    # Docs-team alerts, sent to Slack rather than posted on GitHub.
    notifications: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.add_labels
            or self.remove_labels
            or self.comments
            or self.close
            or self.reopen
            or self.notifications
        )


def business_days_between(start: datetime, end: datetime) -> int:
    """Count weekdays in (start.date(), end.date()]."""
    days = 0
    current = start.date()
    last = end.date()
    while current < last:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days += 1
    return days


def marker_text(name: str) -> str:
    return f"{MARKER_PREFIX}{name} -->"


def parse_marker(body: str) -> str | None:
    start = body.find(MARKER_PREFIX)
    if start < 0:
        return None
    end = body.find(" -->", start)
    if end < 0:
        return None
    return body[start + len(MARKER_PREFIX) : end]


def latest(times: list[datetime]) -> datetime | None:
    return max(times) if times else None


def latest_marker(item: Item, name: str, *, since: datetime | None = None) -> datetime | None:
    return latest(
        [
            marker.at
            for marker in item.markers
            if marker.name == name and (since is None or marker.at >= since)
        ]
    )


def last_author_activity(item: Item) -> datetime | None:
    author = item.author.lower()
    return latest([a.at for a in item.activities if a.actor.lower() == author])


def last_team_feedback(item: Item) -> datetime | None:
    author = item.author.lower()
    return latest(
        [
            a.at
            for a in item.activities
            if a.is_team and a.is_feedback and a.actor.lower() != author
        ]
    )


def has_sme(item: Item) -> bool:
    if item.assignees or item.requested_reviewers:
        return True
    author = item.author.lower()
    return any(a.is_team and a.actor.lower() != author for a in item.activities)


def reviewers(item: Item) -> list[str]:
    """Pending review requests first, then team members who have reviewed."""
    author = item.author.lower()
    names = list(item.requested_reviewers)
    for a in item.activities:
        if a.is_review and a.is_team and a.actor.lower() != author:
            names.append(a.actor)
    return list(dict.fromkeys(names))


def set_status(plan: Plan, item: Item, status: str) -> None:
    for label in (LABEL_AWAITING_AUTHOR, LABEL_AWAITING_REVIEW):
        if label == status and label not in item.labels:
            plan.add_labels.add(label)
        elif label != status and label in item.labels:
            plan.remove_labels.add(label)


def author_mention(item: Item) -> str:
    return f"@{item.author}"


def conflict_body(item: Item) -> str:
    return (
        f"{marker_text(MARKER_CONFLICT)}\n"
        f"{author_mention(item)}, this pull request now has merge conflicts with `main`, "
        "so it can't be merged as-is.\n\n"
        "To fix it, update your branch from `main` and resolve the conflicts:\n\n"
        "```bash\n"
        "git fetch origin\n"
        "git merge origin/main   # or: git rebase origin/main\n"
        "# resolve the conflicted files, then\n"
        "git commit\n"
        "git push\n"
        "```\n\n"
        "GitHub's [guide to resolving merge conflicts]"
        "(https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/"
        "addressing-merge-conflicts/resolving-a-merge-conflict-using-the-command-line) "
        "covers the details. Once you push, this label clears automatically."
    )


def stale_warning_body(item: Item, config: Config) -> str:
    remaining = config.close_business_days - config.warn_business_days
    noun = "pull request" if item.kind == "pr" else "issue"
    return (
        f"{marker_text(MARKER_STALE_WARNING)}\n"
        f"{author_mention(item)}, this {noun} is waiting on you and has had no activity "
        f"from you for {config.warn_business_days} business days. It will be closed in "
        f"{remaining} more business days unless you respond. Any comment, push, or "
        "review from you resets the clock."
    )


def stale_close_body(item: Item, config: Config) -> str:
    noun = "pull request" if item.kind == "pr" else "issue"
    return (
        f"{marker_text(MARKER_STALE_CLOSE)}\n"
        f"Closing this {noun} because it has waited on {author_mention(item)} for "
        f"{config.close_business_days} business days without a response. This isn't a "
        "judgment on the change. Leave a comment here within "
        f"{config.reopen_window_days} days and it will be reopened automatically."
    )


def reviewer_nudge_body(item: Item, config: Config) -> str:
    mentions = " ".join(f"@{name}" for name in reviewers(item))
    return (
        f"{marker_text(MARKER_REVIEWER_NUDGE)}\n"
        f"{author_mention(item)}, this pull request has been waiting on review from "
        f"{mentions} for {config.reviewer_nudge_business_days} business days since your "
        "last update. Please follow up with your reviewers to keep it moving."
    )


def reopened_body(item: Item) -> str:
    return (
        f"{marker_text(MARKER_REOPENED)}\n"
        f"Reopened because {author_mention(item)} responded after the stale closure."
    )


def plan_closed(item: Item, config: Config, now: datetime) -> Plan:
    """Reopen an item this automation closed if the author has since responded."""
    plan = Plan()
    if LABEL_CLOSED_STALE not in item.labels or item.closed_at is None:
        return plan
    if now - item.closed_at > timedelta(days=config.reopen_window_days):
        return plan
    author_at = last_author_activity(item)
    if author_at is None or author_at <= item.closed_at:
        return plan
    plan.reopen = True
    plan.remove_labels.add(LABEL_CLOSED_STALE)
    set_status(plan, item, LABEL_AWAITING_REVIEW)
    plan.comments.append(Comment(MARKER_REOPENED, reopened_body(item)))
    return plan


def plan_open(item: Item, config: Config, now: datetime) -> Plan:
    plan = Plan()
    if item.draft:
        # Drafts are the author's workspace; clear any state we set earlier.
        plan.remove_labels |= item.labels & {
            LABEL_AWAITING_AUTHOR,
            LABEL_AWAITING_REVIEW,
            LABEL_NEEDS_ASSIGNEE,
        }
        return plan

    author_at = last_author_activity(item)
    since_author = author_at or item.created_at

    conflict = item.conflict
    if conflict is None:
        conflict = LABEL_MERGE_CONFLICT in item.labels

    triggers: list[datetime] = []
    if item.kind == "pr":
        if conflict:
            if LABEL_MERGE_CONFLICT not in item.labels:
                plan.add_labels.add(LABEL_MERGE_CONFLICT)
            conflict_at = latest_marker(item, MARKER_CONFLICT, since=since_author)
            if conflict_at is None:
                plan.comments.append(Comment(MARKER_CONFLICT, conflict_body(item)))
                conflict_at = now
            triggers.append(conflict_at)
        elif LABEL_MERGE_CONFLICT in item.labels:
            plan.remove_labels.add(LABEL_MERGE_CONFLICT)

        feedback_at = last_team_feedback(item)
        if feedback_at is not None and feedback_at > since_author:
            triggers.append(feedback_at)
    else:
        # Issue replies are too varied to classify, so a team member opts an
        # issue in by labeling it; the author's next response opts it out.
        labeled_at = item.awaiting_author_labeled_at
        if (
            LABEL_AWAITING_AUTHOR in item.labels
            and labeled_at is not None
            and labeled_at > since_author
        ):
            triggers.append(labeled_at)

    if triggers:
        set_status(plan, item, LABEL_AWAITING_AUTHOR)
        if LABEL_NEEDS_ASSIGNEE in item.labels:
            plan.remove_labels.add(LABEL_NEEDS_ASSIGNEE)
        plan_stale(plan, item, config, now, clock_start=min(triggers))
    else:
        set_status(plan, item, LABEL_AWAITING_REVIEW)
        plan_review_reminder(plan, item, config, now, waiting_since=since_author)
    return plan


def is_close_exempt(item: Item, config: Config) -> bool:
    if item.labels & config.exempt_labels:
        return True
    if item.author.lower() in config.docs_team:
        return True
    return item.kind == "pr" and not has_sme(item)


def plan_stale(
    plan: Plan, item: Item, config: Config, now: datetime, *, clock_start: datetime
) -> None:
    if is_close_exempt(item, config):
        return
    idle = business_days_between(clock_start, now)
    warned_at = latest_marker(item, MARKER_STALE_WARNING, since=clock_start)
    if warned_at is None:
        if idle >= config.warn_business_days:
            plan.comments.append(
                Comment(MARKER_STALE_WARNING, stale_warning_body(item, config))
            )
        return
    # Measure the grace period from the warning so a late warning (for example
    # after a missed run) still leaves the author time to respond.
    grace = config.close_business_days - config.warn_business_days
    if idle >= config.close_business_days and business_days_between(warned_at, now) >= grace:
        plan.comments.append(Comment(MARKER_STALE_CLOSE, stale_close_body(item, config)))
        plan.add_labels.add(LABEL_CLOSED_STALE)
        plan.close = True


def plan_review_reminder(
    plan: Plan, item: Item, config: Config, now: datetime, *, waiting_since: datetime
) -> None:
    waited = business_days_between(waiting_since, now)
    names = reviewers(item) if item.kind == "pr" else []
    unassigned = not has_sme(item) if item.kind == "pr" else not item.assignees

    # The label records that the docs team was alerted, and clears once someone
    # is assigned so a later gap alerts again.
    if not unassigned:
        if LABEL_NEEDS_ASSIGNEE in item.labels:
            plan.remove_labels.add(LABEL_NEEDS_ASSIGNEE)
    elif LABEL_NEEDS_ASSIGNEE not in item.labels and waited >= config.review_reminder_business_days:
        need = "a reviewer" if item.kind == "pr" else "an assignee"
        plan.add_labels.add(LABEL_NEEDS_ASSIGNEE)
        plan.notifications.append(f"needs {need}, waiting {waited} business days")

    if not names or waited < config.reviewer_nudge_business_days:
        return
    if latest_marker(item, MARKER_REVIEWER_NUDGE, since=waiting_since) is not None:
        return
    plan.comments.append(Comment(MARKER_REVIEWER_NUDGE, reviewer_nudge_body(item, config)))
    plan.notifications.append(
        f"nudged author and {', '.join(names)}, waiting on review {waited} business days"
    )


# --- GitHub I/O -------------------------------------------------------------


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class GitHub:
    def __init__(self, repo: str, *, apply: bool) -> None:
        self.repo = repo
        self.apply = apply

    def url(self, path: str, params: dict[str, str | int] | None = None) -> str:
        url = f"{API_ROOT}/repos/{self.repo}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return url

    def get(self, path: str, params: dict[str, str | int] | None = None) -> Any:
        return github_api_utils.request_json(self.url(path, params), user_agent=USER_AGENT)

    def paginate(self, path: str, params: dict[str, str | int] | None = None) -> list[Any]:
        results: list[Any] = []
        page = 1
        while True:
            batch = self.get(path, {**(params or {}), "per_page": 100, "page": page})
            results.extend(batch)
            if len(batch) < 100:
                return results
            page += 1

    def write(self, method: str, path: str, payload: Any = None) -> Any:
        if not self.apply:
            return None
        # Writes are not idempotent (a retried POST can double-comment), so
        # they get a single attempt.
        return github_api_utils.request_json(
            self.url(path),
            user_agent=USER_AGENT,
            method=method,
            payload=payload,
            attempts=1,
        )

    def ensure_labels(self) -> None:
        existing = {label["name"] for label in self.paginate("/labels")}
        for name, (color, description) in STATUS_LABELS.items():
            if name not in existing:
                print(f"create label {name}")
                self.write(
                    "POST",
                    "/labels",
                    {"name": name, "color": color, "description": description},
                )


def addresses_author(body: str, author: str) -> bool:
    """A comment that @-mentions only other people is aimed at them, not the author."""
    mentions = {name.lower() for name in MENTION_PATTERN.findall(body)}
    return not mentions or author.lower() in mentions


def timeline_activities(
    events: list[dict[str, Any]], author: str
) -> tuple[list[Activity], list[Marker], datetime | None]:
    activities: list[Activity] = []
    markers: list[Marker] = []
    labeled_at: datetime | None = None
    for event in events:
        kind = event.get("event")
        if kind == "commented":
            user = event.get("user") or {}
            marker = parse_marker(event.get("body") or "")
            if marker is not None:
                markers.append(Marker(marker, parse_time(event["created_at"])))
                continue
            if user.get("type") == "Bot":
                continue
            activities.append(
                Activity(
                    actor=user.get("login", ""),
                    at=parse_time(event["created_at"]),
                    is_team=event.get("author_association") in TEAM_ASSOCIATIONS,
                    is_feedback=addresses_author(event.get("body") or "", author),
                )
            )
        elif kind == "reviewed":
            user = event.get("user") or {}
            if user.get("type") == "Bot" or not event.get("submitted_at"):
                continue
            activities.append(
                Activity(
                    actor=user.get("login", ""),
                    at=parse_time(event["submitted_at"]),
                    is_team=event.get("author_association") in TEAM_ASSOCIATIONS,
                    is_feedback=event.get("state", "").lower() != "approved",
                    is_review=True,
                )
            )
        elif kind in {"head_ref_force_pushed", "ready_for_review", "reopened"}:
            actor = (event.get("actor") or {}).get("login", "")
            activities.append(
                Activity(
                    actor=actor,
                    at=parse_time(event["created_at"]),
                    is_team=False,
                    is_feedback=False,
                )
            )
        elif kind == "labeled":
            actor = event.get("actor") or {}
            label = (event.get("label") or {}).get("name")
            if label == LABEL_AWAITING_AUTHOR and actor.get("type") != "Bot":
                labeled_at = parse_time(event["created_at"])
    return activities, markers, labeled_at


def pull_activities(
    commits: list[dict[str, Any]], review_comments: list[dict[str, Any]], author: str
) -> list[Activity]:
    """Activity the issue timeline omits: review-thread replies and commit authors."""
    activities: list[Activity] = []
    for commit in commits:
        # Commits without a linked GitHub account are assumed to be the author's.
        # Committer dates update on rebase, so they approximate push time.
        login = (commit.get("author") or {}).get("login") or author
        activities.append(
            Activity(
                actor=login,
                at=parse_time(commit["commit"]["committer"]["date"]),
                is_team=False,
                is_feedback=False,
            )
        )
    for comment in review_comments:
        user = comment.get("user") or {}
        if user.get("type") == "Bot":
            continue
        activities.append(
            Activity(
                actor=user.get("login", ""),
                at=parse_time(comment["created_at"]),
                is_team=comment.get("author_association") in TEAM_ASSOCIATIONS,
                is_feedback=True,
                is_review=True,
            )
        )
    return activities


def load_item(github: GitHub, raw: dict[str, Any]) -> Item:
    number = raw["number"]
    kind: ItemKind = "pr" if "pull_request" in raw else "issue"
    author = raw["user"]["login"]
    events = github.paginate(f"/issues/{number}/timeline")
    activities, markers, labeled_at = timeline_activities(events, author)
    item = Item(
        kind=kind,
        number=number,
        author=author,
        title=raw["title"],
        url=raw["html_url"],
        created_at=parse_time(raw["created_at"]),
        labels={label["name"] for label in raw["labels"]},
        assignees=[assignee["login"] for assignee in raw.get("assignees") or []],
        activities=activities,
        markers=markers,
        awaiting_author_labeled_at=labeled_at,
        closed_at=parse_time(raw["closed_at"]) if raw.get("closed_at") else None,
    )
    if kind == "pr":
        pull = github.get(f"/pulls/{number}")
        item.draft = bool(pull.get("draft"))
        item.requested_reviewers = [r["login"] for r in pull.get("requested_reviewers") or []]
        org = github.repo.split("/")[0]
        item.requested_reviewers += [
            f"{org}/{t['slug']}" for t in pull.get("requested_teams") or []
        ]
        item.activities += pull_activities(
            github.paginate(f"/pulls/{number}/commits"),
            github.paginate(f"/pulls/{number}/comments"),
            author,
        )
        if pull.get("mergeable") is None:
            item.conflict = None
        else:
            item.conflict = pull.get("mergeable_state") == "dirty"
    return item


def apply_plan(github: GitHub, item: Item, plan: Plan) -> None:
    number = item.number
    if plan.reopen:
        path = f"/pulls/{number}" if item.kind == "pr" else f"/issues/{number}"
        github.write("PATCH", path, {"state": "open"})
    for comment in plan.comments:
        github.write("POST", f"/issues/{number}/comments", {"body": comment.body})
    if plan.add_labels:
        github.write("POST", f"/issues/{number}/labels", {"labels": sorted(plan.add_labels)})
    for label in sorted(plan.remove_labels):
        github.write("DELETE", f"/issues/{number}/labels/{urllib.parse.quote(label, safe='')}")
    if plan.close:
        path = f"/pulls/{number}" if item.kind == "pr" else f"/issues/{number}"
        github.write("PATCH", path, {"state": "closed"})


def describe(item: Item, plan: Plan) -> str:
    parts = []
    if plan.reopen:
        parts.append("reopen")
    parts += [f"+{label}" for label in sorted(plan.add_labels)]
    parts += [f"-{label}" for label in sorted(plan.remove_labels)]
    parts += [f"comment:{comment.marker}" for comment in plan.comments]
    if plan.close:
        parts.append("close")
    parts += [f"slack:{note}" for note in plan.notifications]
    return f"{item.kind} #{item.number} (@{item.author}): " + ", ".join(parts)


def slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack_payload(repo: str, alerts: list[tuple[Item, str]]) -> dict[str, str]:
    lines = [f"*Docs follow-ups for {repo}*"]
    for item, note in alerts:
        kind = "PR" if item.kind == "pr" else "Issue"
        link = f"<{item.url}|{kind} #{item.number}: {slack_escape(item.title)}>"
        lines.append(f"• {link} (@{slack_escape(item.author)}): {slack_escape(note)}")
    return {"text": "\n".join(lines)}


def run(
    github: GitHub, config: Config, now: datetime, *, slack_path: Path | None = None
) -> int:
    github.ensure_labels()
    failures = 0
    alerts: list[tuple[Item, str]] = []
    work: list[tuple[dict[str, Any], bool]] = [
        (raw, False) for raw in github.paginate("/issues", {"state": "open"})
    ]
    work += [
        (raw, True)
        for raw in github.paginate(
            "/issues",
            {
                "state": "closed",
                "labels": LABEL_CLOSED_STALE,
                "since": (now - timedelta(days=config.reopen_window_days)).isoformat(),
            },
        )
    ]
    for raw, closed in work:
        try:
            item = load_item(github, raw)
            plan = plan_closed(item, config, now) if closed else plan_open(item, config, now)
            if plan.is_empty():
                continue
            print(describe(item, plan))
            apply_plan(github, item, plan)
            alerts += [(item, note) for note in plan.notifications]
        except RuntimeError as error:
            failures += 1
            print(f"#{raw['number']}: {error}", file=sys.stderr)
    if slack_path is not None and alerts:
        slack_path.write_text(json.dumps(slack_payload(github.repo, alerts)), encoding="utf-8")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--apply", action="store_true", help="write changes to GitHub (default: dry run)"
    )
    parser.add_argument(
        "--slack-payload",
        type=Path,
        help="write docs-team alerts here as a Slack webhook payload (only if any)",
    )
    args = parser.parse_args(argv)
    config = Config.load(args.config)
    github = GitHub(args.repo, apply=args.apply)
    if not args.apply:
        print("dry run: no changes will be written")
    return run(github, config, datetime.now(UTC), slack_path=args.slack_payload)


if __name__ == "__main__":
    raise SystemExit(main())
