#!/usr/bin/env python3
"""Generate the cf-docs weekly contribution report as a self-contained HTML page.

Data comes from the GitHub GraphQL API (through the authenticated `gh` CLI) and from
`origin/main` in the local clone. The layout reuses the stylesheet of the 2026-W37
design sample so every week renders the same way.

Usage: generate_weekly.py [--end 2026-10-05] [--out reports/weekly/2026-10-05/index.html]
Each report covers the seven days ending at noon US Eastern on a Monday, so consecutive
reports neither overlap nor leave gaps. The default is the most recent Monday noon that has passed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import statistics
import subprocess
from zoneinfo import ZoneInfo
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO = "canton-network/cf-docs"
HERE = Path(__file__).resolve().parent
STYLE_SOURCE = HERE / "weekly" / "2026-W37" / "index.html"
UTC = dt.timezone.utc

PRINT_CSS = """
.report a{color:var(--accent-ink);text-decoration:none}
.report a:hover{text-decoration:underline}
@media print{
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  ::-webkit-scrollbar{display:none}
  body{background:#fff;padding:0;font-size:13px}
  .wrap{max-width:none}
  .report{border:0;padding:0}
  /* Paper cannot scroll: let every table use the full width and wrap instead. */
  .tbl-wrap{overflow:visible}
  /* Chrome mis-places content that breaks across pages inside a grid, so print the layout containers as plain blocks. */
  .wrap,.report,section.block,.two,.stack{display:block}
  .report > * + *{margin-top:28px}
  section.block > * + *,.two > * + *{margin-top:14px}
  .stack > * + *{margin-top:6px}
  .two > *{break-inside:avoid}
  .kpis{grid-template-columns:repeat(3,1fr)}
  .kpis.four{grid-template-columns:repeat(4,1fr)}
  .kpi .v{font-size:24px}
  .contribs{grid-template-columns:repeat(4,1fr)}
  .kpis,.stack,.cgroup,.callout,.note,.tbl-wrap,.hbars,tr{break-inside:avoid}
  h2{break-after:avoid}
}
@page{size:A4;margin:14mm 12mm}
"""


# ---------- GitHub ----------

PR_FIELDS = """
  ... on PullRequest {
    number title createdAt mergedAt closedAt updatedAt state isDraft reviewDecision
    author { login __typename }
    reviews(first: 100) { nodes { author { login __typename } state submittedAt } }
  }
"""

ISSUE_FIELDS = """
  ... on Issue {
    number title createdAt closedAt updatedAt state
    author { login __typename }
    labels(first: 10) { nodes { name } }
    comments { totalCount }
  }
"""


def gh_search(query: str, fields: str) -> list[dict]:
    """Run a paginated GraphQL search and return every node."""
    gql = (
        "query($q: String!, $after: String) {"
        "  search(query: $q, type: ISSUE, first: 100, after: $after) {"
        "    pageInfo { hasNextPage endCursor }"
        f"    nodes {{ {fields} }}"
        "  }"
        "}"
    )
    nodes: list[dict] = []
    after: str | None = None
    while True:
        args = ["gh", "api", "graphql", "-f", f"query={gql}", "-f", f"q=repo:{REPO} {query}"]
        if after:
            args += ["-f", f"after={after}"]
        data = json.loads(subprocess.run(args, check=True, capture_output=True, text=True).stdout)
        search = data["data"]["search"]
        nodes += [n for n in search["nodes"] if n]
        if not search["pageInfo"]["hasNextPage"]:
            return nodes
        after = search["pageInfo"]["endCursor"]


def closed_unmerged_since(since: dt.datetime) -> list[dict]:
    """Pull requests closed without merging that were updated at or after `since`.

    GitHub search misses many of these for `closed:` ranges, so this pages through the
    repository's closed pull requests, newest update first, instead.
    """
    owner, name = REPO.split("/")
    gql = (
        "query($owner: String!, $name: String!, $after: String) {"
        "  repository(owner: $owner, name: $name) {"
        "    pullRequests(states: CLOSED, first: 100, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {"
        "      pageInfo { hasNextPage endCursor }"
        f"      nodes {{ {PR_FIELDS} }}"
        "    }"
        "  }"
        "}"
    )
    found: list[dict] = []
    after: str | None = None
    while True:
        args = ["gh", "api", "graphql", "-f", f"query={gql}", "-f", f"owner={owner}", "-f", f"name={name}"]
        if after:
            args += ["-f", f"after={after}"]
        conn = json.loads(subprocess.run(args, check=True, capture_output=True, text=True).stdout)
        conn = conn["data"]["repository"]["pullRequests"]
        for node in conn["nodes"]:
            if ts(node["updatedAt"]) < since:
                return found
            found.append(node)
        if not conn["pageInfo"]["hasNextPage"]:
            return found
        after = conn["pageInfo"]["endCursor"]


def gh_count(query: str) -> int:
    gql = "query($q: String!) { search(query: $q, type: ISSUE, first: 1) { issueCount } }"
    out = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={gql}", "-f", f"q=repo:{REPO} {query}"],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(out)["data"]["search"]["issueCount"]


def ts(value: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def span(start: dt.datetime, end: dt.datetime) -> str:
    """GitHub search range covering [start, end)."""
    last = end - dt.timedelta(seconds=1)
    return f"{start:%Y-%m-%dT%H:%M:%S}+00:00..{last:%Y-%m-%dT%H:%M:%S}+00:00"


# ---------- Affiliation ----------

AFFILIATIONS = ("da", "cf", "ext", "bot")
AFF_LABEL = {"da": "Digital Asset", "cf": "Canton Foundation", "ext": "External", "bot": "Bots"}


@dataclass
class Affiliations:
    da: set[str]
    cf: set[str]
    bots: set[str]
    inferred_da: set[str] = field(default_factory=set)
    unmapped: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, path: Path) -> "Affiliations":
        data = json.loads(path.read_text())
        return cls(set(data["digital_asset"]), set(data["canton_foundation"]), set(data["bots"]))

    def of(self, author: dict | None) -> str:
        if not author:
            return "ext"
        login = author["login"]
        if author.get("__typename") == "Bot" or login.endswith("[bot]") or login in self.bots:
            return "bot"
        if login in self.da:
            return "da"
        if login in self.cf:
            return "cf"
        if looks_like_da(login):
            self.inferred_da.add(login)
            return "da"
        self.unmapped.add(login)
        return "ext"


def looks_like_da(login: str) -> bool:
    """Digital Asset logins conventionally carry a -da / da- / DA marker, in any case."""
    lowered = login.lower()
    return lowered.endswith("-da") or lowered.startswith("da-") or login.endswith("DA")


def login(node: dict) -> str:
    return (node.get("author") or {}).get("login", "ghost")


# ---------- Week ----------

EASTERN = ZoneInfo("America/New_York")
CUTOFF = dt.time(12)


def window(end_date: str | None, until: str | None = None) -> tuple[dt.date, dt.datetime, dt.datetime]:
    """Return the Monday and the UTC [start, end) of the week ending at noon Eastern that Monday.

    `until` (an Eastern local time such as 2026-10-05T13:00) is for one-off reviews: the window
    still starts at the previous Monday noon but ends at that time instead.
    """
    if until:
        stop = dt.datetime.fromisoformat(until).replace(tzinfo=EASTERN)
        monday = stop.date() - dt.timedelta(days=stop.weekday())
        if stop <= dt.datetime.combine(monday, CUTOFF, EASTERN):
            monday -= dt.timedelta(days=7)
        return monday, monday_noon(monday - dt.timedelta(days=7)), stop.astimezone(UTC)
    if end_date:
        monday = dt.date.fromisoformat(end_date)
        if monday.weekday() != 0:
            raise SystemExit("--end must be a Monday, such as 2026-10-05")
    else:
        now = dt.datetime.now(EASTERN)
        monday = now.date() - dt.timedelta(days=now.weekday())
        if now < dt.datetime.combine(monday, CUTOFF, EASTERN):
            monday -= dt.timedelta(days=7)
    return monday, monday_noon(monday - dt.timedelta(days=7)), monday_noon(monday)


def monday_noon(day: dt.date) -> dt.datetime:
    # Built from the local date so daylight-saving changes cannot open a gap between weeks.
    return dt.datetime.combine(day, CUTOFF, EASTERN).astimezone(UTC)


def title_range(start: dt.datetime, end: dt.datetime) -> str:
    s, e = start.astimezone(EASTERN), end.astimezone(EASTERN)
    if s.year != e.year:
        return f"{s:%-d %B %Y} – {e:%-d %B %Y}"
    if s.month != e.month:
        return f"{s:%-d %B} – {e:%-d %B %Y}"
    return f"{s:%-d} – {e:%-d %B %Y}"


def range_label(start: dt.datetime, end: dt.datetime) -> str:
    s, e = start.astimezone(EASTERN), end.astimezone(EASTERN)
    if s.time() == e.time() == CUTOFF:
        return f"{s:%a %-d %b} – {e:%a %-d %b}, noon to noon ET"
    return f"{s:%a %-d %b %-I:%M %p} – {e:%a %-d %b %-I:%M %p} ET"


# ---------- Measures ----------

def hours(delta: dt.timedelta) -> float:
    return delta.total_seconds() / 3600


def fmt_h(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value / 24:.1f} d" if value >= 48 else f"{value:.1f} h"


def p90(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=10, method="inclusive")[-1]


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def peer_reviews(pr: dict) -> list[dict]:
    author = login(pr)
    return [
        r for r in pr["reviews"]["nodes"]
        if r.get("submittedAt") and login(r) != author and (r.get("author") or {}).get("__typename") != "Bot"
    ]


def first_review_hours(pr: dict) -> float | None:
    reviews = peer_reviews(pr)
    if not reviews:
        return None
    first = min(ts(r["submittedAt"]) for r in reviews)
    return hours(first - ts(pr["createdAt"]))


def age_buckets(days: list[int]) -> list[int]:
    return [
        sum(d < 7 for d in days),
        sum(7 <= d < 30 for d in days),
        sum(30 <= d < 90 for d in days),
        sum(d >= 90 for d in days),
    ]


def pr_state(pr: dict) -> tuple[str, str]:
    if pr["isDraft"]:
        return "draft", ""
    decision = pr.get("reviewDecision")
    if decision == "APPROVED":
        return "approved, unmerged", "crit"
    if decision == "CHANGES_REQUESTED":
        return "changes requested", "warn"
    return "review required", "warn"


# ---------- Content footprint (git) ----------

def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, cwd=HERE.parent).stdout


def commit_before(moment: dt.datetime) -> str:
    return git("rev-list", "-1", f"--before={moment.isoformat()}", "origin/main").strip()


def page_count(commit: str) -> int:
    files = git("ls-tree", "-r", "--name-only", commit, "--", "docs-main").splitlines()
    return sum(f.endswith(".mdx") for f in files)


def content_footprint(start: dt.datetime, end: dt.datetime) -> dict:
    base, head = commit_before(start), commit_before(end)
    log = git(
        "log", f"{base}..{head}", "--no-merges", "-M", "--name-status",
        "--format=@@%an\x1f%h\x1f%s", "--", "docs-main",
    )
    added = removed = renamed = 0
    edited: set[str] = set()
    per_commit: Counter = Counter()
    subjects: dict[str, str] = {}
    is_bot = False
    commit = ""
    for line in log.splitlines():
        if line.startswith("@@"):
            name, commit, subjects_line = line[2:].split("\x1f", 2)
            subjects[commit] = subjects_line
            is_bot = "[bot]" in name or "generated-docs-merger" in name
            continue
        if is_bot or not line.strip():
            continue
        status, *paths = line.split("\t")
        if not paths[-1].endswith(".mdx"):
            continue
        if status == "A":
            added += 1
        elif status == "D":
            removed += 1
        elif status == "M":
            edited.add(paths[-1])
            per_commit[commit] += 1
        elif status.startswith("R"):
            renamed += 1
    pages_start, pages_end = page_count(base), page_count(head)
    return {
        "pages": pages_end,
        "net": pages_end - pages_start,
        "added": added,
        "removed": removed,
        "edited": len(edited),
        "renamed": renamed,
        "head": head[:8],
        "largest": (*per_commit.most_common(1)[0], subjects[per_commit.most_common(1)[0][0]]) if per_commit else None,
    }


# ---------- HTML helpers ----------

def e(value: object) -> str:
    return html.escape(str(value))


def signed(n: int | float, unit: str = "") -> str:
    if n == 0:
        return f"0{unit}"
    return f"{'+' if n > 0 else '−'}{abs(n):g}{unit}" if isinstance(n, float) else f"{'+' if n > 0 else '−'}{abs(n):,}{unit}"


def trend(cur: int, prev: int) -> str:
    if cur > prev:
        return f'<div class="d up">▲ from {prev}</div>'
    if cur < prev:
        return f'<div class="d down">▼ from {prev}</div>'
    return f'<div class="d">same as last week ({prev})</div>'


def kpi(value: str, label: str, detail: str) -> str:
    return f'<div class="kpi"><div class="v num">{value}</div><div class="l">{e(label)}</div>{detail}</div>'


def clip(title: str, limit: int = 70) -> str:
    return e(title if len(title) <= limit else title[: limit - 1].rstrip() + "…")


def num_ref(n: int, kind: str = "issues") -> str:
    """#n linked to GitHub; kind is "pull" for pull requests, "issues" for issues."""
    return f'<a class="mono" href="https://github.com/{REPO}/{kind}/{n}">#{n}</a>'


def stacked_bar(label: str, counts: Counter) -> str:
    total = sum(counts.values())
    spans = "".join(
        f'<span class="sw-{a}" style="width:{100 * counts[a] / total:.1f}%" title="{AFF_LABEL[a]} · {counts[a]}"></span>'
        for a in AFFILIATIONS if counts[a]
    ) if total else ""
    aria = ", ".join(f"{counts[a]} {AFF_LABEL[a]}" for a in AFFILIATIONS)
    return (
        f'<div class="rowlabel"><span>{e(label)}</span><b class="num">{total}</b></div>'
        f'<div class="bar" role="img" aria-label="{e(label)}: {aria}">{spans}</div>'
    )


def table(head: list[str], rows: list[list[str]], right: set[int] = frozenset(), body_class: str = "") -> str:
    th = "".join(f'<th{" class=\"r\"" if i in right else ""}>{h}</th>' for i, h in enumerate(head))
    trs = "".join(
        "<tr>" + "".join(f'<td{" class=\"r\"" if i in right else ""}>{c}</td>' for i, c in enumerate(r)) + "</tr>"
        for r in rows
    )
    thead = f"<thead><tr>{th}</tr></thead>" if head else ""
    cls = f' class="{body_class}"' if body_class else ""
    return f'<div class="tbl-wrap"><table>{thead}<tbody{cls}>{trs}</tbody></table></div>'


# ---------- Report ----------

def build(monday: dt.date, start: dt.datetime, end: dt.datetime) -> str:
    aff = Affiliations.load(HERE / "contributors.json")
    now = dt.datetime.now(UTC)
    prev_start = monday_noon(monday - dt.timedelta(days=14))
    cur, prev = span(start, end), span(prev_start, start)

    opened = gh_search(f"is:pr created:{cur}", PR_FIELDS)
    opened_prev = gh_search(f"is:pr created:{prev}", PR_FIELDS)
    merged = gh_search(f"is:pr merged:{cur}", PR_FIELDS)
    merged_prev = gh_search(f"is:pr merged:{prev}", PR_FIELDS)
    recently_closed = closed_unmerged_since(prev_start)
    closed = [p for p in recently_closed if start <= ts(p["closedAt"]) < end]
    closed_prev_prs = [p for p in recently_closed if prev_start <= ts(p["closedAt"]) < start]
    open_prs = gh_search("is:pr is:open", PR_FIELDS)

    issues_opened = gh_search(f"is:issue created:{cur}", ISSUE_FIELDS)
    issues_closed = gh_count(f"is:issue closed:{cur}")
    open_issues = gh_search("is:issue is:open", ISSUE_FIELDS)

    def backlog_at(moment: dt.datetime) -> int:
        stamp = f"{moment:%Y-%m-%dT%H:%M:%S}+00:00"
        still_open = sum(ts(i["createdAt"]) < moment for i in open_issues)
        return still_open + gh_count(f"is:issue created:<{stamp} closed:>={stamp}")

    backlog_start, backlog_end = backlog_at(start), backlog_at(end)

    def by_aff(prs: list[dict]) -> Counter:
        return Counter(aff.of(p.get("author")) for p in prs)

    people = lambda prs: [p for p in prs if aff.of(p.get("author")) != "bot"]  # noqa: E731
    opened_aff, merged_aff = by_aff(opened), by_aff(merged)
    opened_people, opened_people_prev = people(opened), people(opened_prev)
    merged_people, merged_people_prev = people(merged), people(merged_prev)
    closed_people = people(closed)
    closed_prev = len(people(closed_prev_prs))

    def merge_hours(prs: list[dict]) -> float | None:
        return median([hours(ts(p["mergedAt"]) - ts(p["createdAt"])) for p in prs])

    # Contributors
    authors: dict[str, Counter] = defaultdict(Counter)
    for p in opened:
        authors[aff.of(p.get("author"))][login(p)] += 1
    cur_people = {login(p) for p in opened_people}
    prev_people = {login(p) for p in opened_people_prev}
    first_timers = sorted(
        a for a in cur_people
        if gh_count(f"is:pr author:{a} created:<{start:%Y-%m-%dT%H:%M:%S}+00:00") == 0
    )

    # Reviews on people's PRs opened this week
    reviews = [r for p in opened_people for r in peer_reviews(p)]
    reviewers = Counter(login(r) for r in reviews)
    approvals = [r for r in reviews if r["state"] == "APPROVED"]
    ttfr = [h for h in (first_review_hours(p) for p in opened_people) if h is not None]
    unreviewed_merged = [p for p in merged_people if not peer_reviews(p)]

    # Staleness
    def untouched(node: dict) -> int:
        return (now - ts(node["updatedAt"])).days

    # A draft is still being written, so it is never counted as stale.
    ready_prs = [p for p in open_prs if not p["isDraft"]]
    drafts = len(open_prs) - len(ready_prs)
    open_pr_days = [untouched(p) for p in ready_prs]
    open_issue_days = [untouched(i) for i in open_issues]
    stalest_prs = sorted(ready_prs, key=lambda p: p["updatedAt"])[:5]
    stalest_issues = sorted(open_issues, key=lambda i: i["updatedAt"])[:5]
    approved_open = sorted(
        (p for p in open_prs if p.get("reviewDecision") == "APPROVED" and not p["isDraft"]),
        key=lambda p: p["updatedAt"],
    )
    zero_comment = sum(i["comments"]["totalCount"] == 0 for i in open_issues)

    content = content_footprint(start, end)

    # ----- assemble -----
    week_title = title_range(start, end)
    prev_label = range_label(prev_start, start)
    stale_prs_30 = sum(d >= 30 for d in open_pr_days)
    oldest_pr = max(open_pr_days, default=0)

    kpis = "".join([
        kpi(str(len(opened_people)), "PRs opened (people)", trend(len(opened_people), len(opened_people_prev))),
        kpi(str(len(merged_people)), "PRs merged (people)", trend(len(merged_people), len(merged_people_prev))),
        kpi(str(len(closed_people)), "PRs closed unmerged", f'<div class="d">{closed_prev} last week</div>'),
        kpi(
            f"{len(issues_opened)} / {issues_closed}", "Issues opened / closed",
            f'<div class="d {"up" if backlog_end < backlog_start else "down" if backlog_end > backlog_start else ""}">'
            f"backlog {backlog_start} → {backlog_end}</div>",
        ),
        kpi(fmt_h(median(ttfr)), "Median time to first review", f'<div class="d">p90 {fmt_h(p90(ttfr))}</div>'),
        kpi(str(stale_prs_30), "Open PRs stale 30+ d", f'<div class="d">oldest {oldest_pr} d · drafts excluded</div>'),
    ])

    still_open = sum(p["state"] == "OPEN" for p in opened)
    merged_of_opened = sum(p["state"] == "MERGED" for p in opened)
    closed_of_opened = sum(p["state"] == "CLOSED" for p in opened)
    legend = "".join(
        f'<span><i class="sw-{a}"></i>{AFF_LABEL[a]} · {opened_aff[a]} / {merged_aff[a]}</span>' for a in AFFILIATIONS
    )
    wow_rows = [
        ["Opened by people", str(len(opened_people)), str(len(opened_people_prev)), signed(len(opened_people) - len(opened_people_prev))],
        ["Merged (people)", str(len(merged_people)), str(len(merged_people_prev)), signed(len(merged_people) - len(merged_people_prev))],
        ["Closed unmerged (people)", str(len(closed_people)), str(closed_prev), "—"],
        ["Opened by bots", str(opened_aff["bot"]), str(len(opened_prev) - len(opened_people_prev)),
         signed(opened_aff["bot"] - (len(opened_prev) - len(opened_people_prev)))],
        ["Median open → merge (people)", fmt_h(merge_hours(merged_people)), fmt_h(merge_hours(merged_people_prev)), ""],
    ]

    pr_section = f"""
    <section class="block">
      <h2>Pull requests <small>{len(opened)} opened this week · of those {merged_of_opened} merged, {closed_of_opened} closed, {still_open} still open</small></h2>
      <div class="two">
        <div class="stack">
          {stacked_bar("Opened, by author type", opened_aff)}
          {stacked_bar("Merged, by author type", merged_aff)}
          <div class="legend">{legend}</div>
        </div>
        <div>{table(["", "This week", "Last week", "Change"], wow_rows, right={1, 2, 3}, body_class="num")}</div>
      </div>
    </section>"""

    def group(a: str) -> str:
        members = authors.get(a, Counter())
        if not members:
            items = f'<li class="c">No {AFF_LABEL[a].lower()} contributors this week.</li>'
        else:
            items = "".join(
                f'<li><span class="mono">{e(name)}</span> <span class="c">· {n}{(" PR" if n == 1 else " PRs") if i == 0 else ""}</span></li>'
                for i, (name, n) in enumerate(members.most_common())
            )
        return (
            f'<div class="cgroup"><h3><i class="sw-{a}"></i>{AFF_LABEL[a]}</h3>'
            f'<div class="count num">{len(members)}</div><ul>{items}</ul></div>'
        )

    gone = sorted(prev_people - cur_people)
    contrib_section = f"""
    <section class="block">
      <h2>Contributors <small>{len(cur_people)} people opened a PR · {len(reviewers)} people reviewed one · {len(authors.get("ext", {}))} external</small></h2>
      <div class="contribs">{"".join(group(a) for a in AFFILIATIONS)}</div>
      <p class="note"><b>First-time contributors this week:</b> {", ".join(f'<span class="mono">{e(a)}</span>' for a in first_timers) or "none"}.
      <b>Active last week but not this week:</b> {len(gone)} {"person" if len(gone) == 1 else "people"}.</p>
    </section>"""

    top = reviewers.most_common(5)
    rest = sum(reviewers.values()) - sum(n for _, n in top)
    peak = top[0][1] if top else 1
    bars = "".join(
        f'<span class="k mono">{e(name)}</span><div class="t" title="{n} reviews"><i style="width:{100 * n / peak:.0f}%"></i></div><span class="n">{n}</span>'
        for name, n in top
    )
    if rest:
        others = len(reviewers) - len(top)
        bars += f'<span class="k">{others} others</span><div class="t" title="{rest} reviews"><i style="width:{100 * rest / peak:.0f}%"></i></div><span class="n">{rest}</span>'
    share = 100 * top[0][1] / sum(reviewers.values()) if top else 0
    concentration = (
        f'<p class="note" style="margin-top:10px">The top reviewer carried <b>{share:.0f} %</b> of review activity. '
        "Under 40 % is the target; above 50 % two weeks running is a staffing flag.</p>"
        if top else '<p class="note">No reviews on PRs opened this week.</p>'
    )
    unreviewed = " ".join(f'<span class="pill">{num_ref(p["number"], "pull")}</span>' for p in unreviewed_merged[:6])
    review_rows = [
        ["Merged PRs with at least one review", f"{len(merged_people) - len(unreviewed_merged)} of {len(merged_people)}"],
        ["Merged with no review", f"{len(unreviewed_merged)} {unreviewed}"],
        ["Median time to first review", fmt_h(median(ttfr))],
        ["p90 time to first review", fmt_h(p90(ttfr))],
        ["Approvals given", f"{len(approvals)} by {len({login(r) for r in approvals})} people"],
        ["Changes requested", str(sum(r["state"] == "CHANGES_REQUESTED" for r in reviews))],
    ]
    review_section = f"""
    <section class="block">
      <h2>Review health <small>{len(reviews)} reviews on people's PRs opened this week</small></h2>
      <div class="two">
        <div>{table([], review_rows, right={1}, body_class="num")}</div>
        <div>
          <div class="rowlabel" style="margin-bottom:8px"><span>Reviews by reviewer</span><b>concentration</b></div>
          <div class="hbars num">{bars}</div>
          {concentration}
        </div>
      </div>
    </section>"""

    def ages(label: str, days: list[int]) -> str:
        cells = "".join(
            f'<div class="age a{i + 1}"><div class="v">{n}</div><div class="l">{lab}</div></div>'
            for i, (n, lab) in enumerate(zip(age_buckets(days), ["under 7 d", "7 – 30 d", "30 – 90 d", "over 90 d"]))
        )
        return f'<div class="stack"><div class="rowlabel"><span>{label}</span><b class="num">{len(days)}</b></div><div class="ages num">{cells}</div></div>'

    def pr_row(p: dict) -> list[str]:
        state, tone = pr_state(p)
        return [
            f'{num_ref(p["number"], "pull")} <span class="title">{clip(p["title"])}</span>',
            f'<span class="mono">{e(login(p))}</span>',
            f"{untouched(p)} d",
            f'<span class="pill {tone}">{state}</span>',
        ]

    def issue_row(i: dict) -> list[str]:
        return [
            f'{num_ref(i["number"])} <span class="title">{clip(i["title"])}</span>',
            f'<span class="mono">{e(login(i))}</span>',
            f"{untouched(i)} d",
            str(i["comments"]["totalCount"]),
        ]

    approved_note = ""
    if approved_open:
        refs = ", ".join(f'{num_ref(p["number"], "pull")} ({untouched(p)} d)' for p in approved_open[:8])
        approved_note = (
            f"<b>{len(approved_open)} PR{'s are' if len(approved_open) != 1 else ' is'} approved but not merged:</b> {refs}. "
            "Finished work not shipping is the cheapest thing on this page to fix. "
        )
    stale_section = f"""
    <section class="block">
      <h2>Staleness <small>days since the item was last touched, as of {now:%-d %b} · {drafts} draft PR{"" if drafts == 1 else "s"} not counted</small></h2>
      <div class="two">{ages("Open pull requests (not drafts)", open_pr_days)}{ages("Open issues", open_issue_days)}</div>
      <div class="two">
        <div><div class="rowlabel" style="margin-bottom:6px"><span>Stalest open PRs (not drafts)</span></div>
          {table(["PR", "Author", "Untouched", "State"], [pr_row(p) for p in stalest_prs], right={2})}</div>
        <div><div class="rowlabel" style="margin-bottom:6px"><span>Stalest open issues</span></div>
          {table(["Issue", "Filed by", "Untouched", "Comments"], [issue_row(i) for i in stalest_issues], right={2, 3})}</div>
      </div>
      <p class="callout">{approved_note}<b>{zero_comment} of {len(open_issues)} open issues have never received a comment.</b></p>
    </section>"""

    dominant_note = ""
    largest = content["largest"]
    if largest and content["edited"] and largest[1] / content["edited"] > 0.25:
        sha, count, subject = largest
        dominant_note = (
            f'<p class="note"><b>Read with care:</b> one commit, <a class="mono" href="https://github.com/{REPO}/commit/{e(sha)}">{e(sha)}</a> '
            f'"{e(subject)}", edited {count:,} of the {content["edited"]:,} pages. '
            "Pages edited mostly reflects that single change this week.</p>"
        )
    content_section = f"""
    <section class="block">
      <h2>Content footprint <small>.mdx pages under <span class="mono">docs-main</span> on <span class="mono">main</span></small></h2>
      <div class="kpis four">
        {kpi(f"{content['pages']:,}", "Pages total", f'<div class="d">at {content["head"]}</div>')}
        {kpi(signed(content["net"]), "Net pages", '<div class="d">all commits</div>')}
        {kpi(str(content["added"]), "Pages added", f'<div class="d">{content["removed"]} removed · people only</div>')}
        {kpi(str(content["edited"]), "Pages edited", f'<div class="d">{content["renamed"]} renamed · people only</div>')}
      </div>
      {dominant_note}
    </section>"""

    labels = Counter(lab["name"] for i in issues_opened for lab in i["labels"]["nodes"])
    unlabelled = sum(not i["labels"]["nodes"] for i in issues_opened)
    readers = sum(aff.of(i.get("author")) == "ext" for i in issues_opened)
    open_ages = [(now - ts(i["createdAt"])).days for i in open_issues]
    issue_rows = [
        [
            f'{num_ref(i["number"])} <span class="title">{clip(i["title"])}</span>',
            f'<span class="mono">{e(login(i))}</span>',
            " ".join(f'<span class="pill">{e(lab["name"])}</span>' for lab in i["labels"]["nodes"]) or '<span class="c">—</span>',
            i["state"].lower(),
        ]
        for i in sorted(issues_opened, key=lambda i: -i["number"])[:15]
    ]
    more = f'<p class="note">{len(issues_opened) - 15} more not shown.</p>' if len(issues_opened) > 15 else ""
    issue_stats = [
        ["Filed by readers (non-team)", f"{readers} of {len(issues_opened)}"],
        ["Labelled bug", str(labels["bug"])],
        ["Labelled enhancement", str(labels["enhancement"])],
        ["Unlabelled", f"{unlabelled} of {len(issues_opened)}"],
        ["Open issues with zero comments", f"{zero_comment} of {len(open_issues)}"],
        ["Median age of open issues", f"{median(open_ages):.0f} d" if open_ages else "—"],
    ]
    issues_section = f"""
    <section class="block">
      <h2>Issues <small>{len(issues_opened)} opened · {issues_closed} closed · {len(open_issues)} open</small></h2>
      <div class="two">
        <div>{table(["Opened this week", "By", "Label", "State"], issue_rows)}{more}</div>
        <div>{table([], issue_stats, right={1}, body_class="num")}</div>
      </div>
    </section>"""

    mapping_note = ""
    if aff.inferred_da or aff.unmapped:
        parts = []
        if aff.inferred_da:
            parts.append("counted as Digital Asset from the login pattern: " + ", ".join(f'<span class="mono">{e(x)}</span>' for x in sorted(aff.inferred_da)))
        if aff.unmapped:
            parts.append("counted as external because they are not in the mapping: " + ", ".join(f'<span class="mono">{e(x)}</span>' for x in sorted(aff.unmapped)))
        mapping_note = f'<div><dt>Unmapped logins.</dt> <dd>{"; ".join(parts)}.</dd></div>'

    method = f"""
    <dl class="method">
      <div><dt>People vs bots.</dt> <dd>Accounts GitHub marks as bots, plus the bot list in <span class="mono">contributors.json</span>. "People" rows exclude them.</dd></div>
      <div><dt>Affiliation.</dt> <dd>From <span class="mono">contributors.json</span>, which maps logins to Digital Asset or Canton Foundation. Unlisted logins ending in <span class="mono">-da</span> or <span class="mono">DA</span>, or starting with <span class="mono">da-</span>, count as Digital Asset; other unlisted logins count as external.</dd></div>
      {mapping_note}
      <div><dt>Stale.</dt> <dd>Only pull requests that are not drafts count toward staleness; drafts are still being written.</dd></div>
      <div><dt>Untouched.</dt> <dd>Days since GitHub's <span class="mono">updatedAt</span> on the PR or issue: any comment, commit, review, or label change resets it.</dd></div>
      <div><dt>Time to first review.</dt> <dd>PR opened to first submitted review by someone other than the author, on people's PRs opened in the week that received one.</dd></div>
      <div><dt>Week.</dt> <dd>Seven days ending Monday 12:00 US Eastern; each report starts where the previous one ended. Week-over-week compares the preceding seven days.</dd></div>
    </dl>"""

    style = re.search(r"<style>(.*?)</style>", STYLE_SOURCE.read_text(), re.S)[1] + PRINT_CSS
    return f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>cf-docs weekly · {start.astimezone(EASTERN):%Y-%m-%d} to {monday:%Y-%m-%d}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{style}</style>
</head>
<body>
<div class="wrap">
  <div class="report">
    <header class="masthead">
      <div class="eyebrow">canton-network / cf-docs · contribution report</div>
      <h1>{e(week_title)}</h1>
      <div class="range"><b>{e(range_label(start, end))}</b>. Compared with <b>{e(prev_label)}</b>. Generated {now:%-d %b %H:%M} UTC from GitHub and the <span class="mono">main</span> branch.</div>
    </header>
    <div class="kpis">{kpis}</div>
    {pr_section}
    {contrib_section}
    {review_section}
    {stale_section}
    {content_section}
    {issues_section}
    {method}
  </div>
</div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--end", help="Monday the window ends on, such as 2026-10-05 (default: most recent Monday noon ET)")
    parser.add_argument("--until", help="one-off review: end at this Eastern time, such as 2026-10-05T13:00")
    parser.add_argument("--out", type=Path, help="output path (default: reports/weekly/<week>/index.html)")
    args = parser.parse_args()
    monday, start, end = window(args.end, args.until)
    out = args.out or HERE / "weekly" / f"{monday:%Y-%m-%d}" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(monday, start, end))
    print(out)


if __name__ == "__main__":
    main()
