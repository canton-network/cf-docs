#!/usr/bin/env python3
"""Build or update the cf-docs contribution tracker workbook.

The workbook has three interactive report tabs (Activity, People, Open work; see
tracker_reports.py) and data tabs: every pull request, issue and review from GitHub, plus a
Contributors tab whose affiliations people can edit.

With --from, the existing tracker (an .xlsx export of the Google Sheet) is read back first:
its data is kept, only pull requests and issues updated since its last refresh are fetched
again, and its Contributors affiliations are preserved. The report tabs are regenerated.
Next to the output it writes <out>.expected.json: what the default Activity view should show,
computed here independently, for checking Google's numbers after upload.

Usage: build_tracker.py [--from current.xlsx] [--out new.xlsx]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from generate_weekly import CUTOFF, EASTERN, REPO, UTC, Affiliations, looks_like_da
from tracker_reports import Ranges, add_reports

HERE = Path(__file__).resolve().parent
OWNER, NAME = REPO.split("/")

FONT = "Arial"
INK, INK2, INK3 = "141A24", "4B5566", "7D8798"
ACCENT = "1C5CAB"
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
DATE_FMT = "yyyy-mm-dd hh:mm"

# Review windows look back this far past the last refresh, to catch slow-to-index updates.
REFETCH_OVERLAP = dt.timedelta(days=2)


# ---------- GitHub ----------

# Timeline events that count as someone working on an item. Bots, including the
# follow-up automation (github-actions), also produce these; they are filtered out when
# the records are built, so "untouched" means untouched by a person.
ACTOR_EVENTS = ["LabeledEvent", "UnlabeledEvent", "ClosedEvent", "ReopenedEvent", "AssignedEvent",
                "RenamedTitleEvent", "CrossReferencedEvent"]
PR_ACTOR_EVENTS = ACTOR_EVENTS + ["MergedEvent", "ReadyForReviewEvent", "ConvertToDraftEvent",
                                  "ReviewRequestedEvent", "HeadRefForcePushedEvent"]


def enum_name(typename: str) -> str:
    return "".join("_" + c if c.isupper() else c for c in typename).lstrip("_").upper()


def timeline(events: list[str], extra_types: list[str], extra_fragments: str) -> str:
    types = ", ".join(enum_name(t) for t in ["IssueComment"] + extra_types + events)
    fragments = "".join(f" ... on {t} {{ createdAt actor {{ login __typename }} }}" for t in events)
    return (f"timelineItems(last: 50, itemTypes: [{types}]) {{ nodes {{ __typename"
            f" ... on IssueComment {{ createdAt author {{ login __typename }} }}{extra_fragments}{fragments} }} }}")


PR_NODE = f"""
  number title url createdAt mergedAt closedAt updatedAt state isDraft reviewDecision
  author {{ login __typename }}
  reviews(first: 100) {{ nodes {{ author {{ login __typename }} state submittedAt }} }}
  {timeline(PR_ACTOR_EVENTS, ["PullRequestReview", "PullRequestCommit"],
            " ... on PullRequestReview { submittedAt author { login __typename } }"
            " ... on PullRequestCommit { commit { committedDate } }")}
"""

ISSUE_NODE = f"""
  number title url createdAt closedAt updatedAt state
  author {{ login __typename }}
  labels(first: 10) {{ nodes {{ name }} }}
  comments(last: 100) {{ totalCount nodes {{ author {{ login __typename }} }} }}
  {timeline(ACTOR_EVENTS, [], "")}
"""

AUTOMATION = set(json.loads((HERE / "contributors.json").read_text())["bots"])


def is_automation(account: dict | None) -> bool:
    if not account:
        return False  # deleted accounts show as null: a person, as far as we can tell
    login = account.get("login", "")
    return account.get("__typename") == "Bot" or login.endswith("[bot]") or login in AUTOMATION


def human_activity(node: dict) -> tuple[dt.datetime, bool]:
    """Last time a person acted on the item (at least its creation), and whether a bot closed it last."""
    latest = utc(node["createdAt"])
    last_close = None
    for event in node["timelineItems"]["nodes"]:
        kind = event["__typename"]
        if kind == "PullRequestCommit":
            when, who = event["commit"]["committedDate"], {}
        else:
            when = event.get("createdAt") or event.get("submittedAt")
            who = event.get("actor") if "actor" in event else event.get("author")
        if kind == "ClosedEvent":
            last_close = who
        if when and not is_automation(who):
            latest = max(latest, utc(when))
    closed_by_bot = node["state"] == "CLOSED" and is_automation(last_close) if last_close is not None else False
    return latest, closed_by_bot


def fetch_updated(field: str, node: str, since: dt.datetime | None) -> list[dict]:
    """Pull requests or issues updated at or after `since` (all of them when None), newest first."""
    query = (
        "query($owner: String!, $name: String!, $after: String, $first: Int!) {"
        "  repository(owner: $owner, name: $name) {"
        f"    {field}(first: $first, after: $after, orderBy: {{field: UPDATED_AT, direction: DESC}}) {{"
        "      pageInfo { hasNextPage endCursor }"
        f"      nodes {{ {node} }}"
        "    }"
        "  }"
        "}"
    )
    nodes: list[dict] = []
    after: str | None = None
    while True:
        conn = graphql_page(query, field, after)
        for item in conn["nodes"]:
            if since and utc(item["updatedAt"]) < since:
                return nodes
            nodes.append(item)
        if not conn["pageInfo"]["hasNextPage"]:
            return nodes
        after = conn["pageInfo"]["endCursor"]


def graphql_page(query: str, field: str, after: str | None) -> dict:
    """One page, retried with smaller pages: GitHub times out on large pages of timelines."""
    error = ""
    for attempt, first in enumerate((100, 50, 25, 25, 10)):
        args = ["gh", "api", "graphql", "-f", f"query={query}", "-f", f"owner={OWNER}", "-f", f"name={NAME}",
                "-F", f"first={first}"]
        if after:
            args += ["-f", f"after={after}"]
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get("data") and data["data"]["repository"]:
                return data["data"]["repository"][field]
        error = (result.stderr or result.stdout).strip()[:500]
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"GitHub query for {field} failed after retries: {error}")


def utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def eastern(value: str | None) -> dt.datetime | None:
    """GitHub UTC timestamp as a naive US Eastern datetime; spreadsheets have no time zones."""
    return utc(value).astimezone(EASTERN).replace(tzinfo=None) if value else None


def author_of(node: dict) -> tuple[str, bool]:
    author = node.get("author") or {}
    return author.get("login", "ghost"), author.get("__typename") == "Bot"


def pr_record(node: dict) -> tuple[dict, list[dict]]:
    author, _ = author_of(node)
    reviews = []
    for r in node["reviews"]["nodes"]:
        reviewer, reviewer_bot = author_of(r)
        if r.get("submittedAt") and reviewer != author:
            reviews.append({"pr": node["number"], "url": node["url"], "reviewer": reviewer,
                            "bot": reviewer_bot, "state": r["state"], "submitted": eastern(r["submittedAt"])})
    peer = [r for r in reviews if not r["bot"]]
    human, closed_by_bot = human_activity(node)
    return {
        "number": node["number"], "title": node["title"], "url": node["url"], "author": author,
        "created": eastern(node["createdAt"]), "merged": eastern(node["mergedAt"]),
        "closed": eastern(node["closedAt"]), "state": node["state"], "draft": node["isDraft"],
        "updated": eastern(node["updatedAt"]),
        "first_review": min((r["submitted"] for r in peer), default=None),
        "peer_reviews": len(peer), "decision": node.get("reviewDecision") or "",
        "human_updated": eastern(human.isoformat()), "auto_closed": closed_by_bot,
    }, reviews


def issue_record(node: dict) -> dict:
    human, closed_by_bot = human_activity(node)
    return {
        "number": node["number"], "title": node["title"], "url": node["url"], "author": author_of(node)[0],
        "created": eastern(node["createdAt"]), "closed": eastern(node["closedAt"]), "state": node["state"],
        "labels": ", ".join(lab["name"] for lab in node["labels"]["nodes"]),
        "comments": sum(not is_automation(c.get("author")) for c in node["comments"]["nodes"]),
        "updated": eastern(node["updatedAt"]),
        "human_updated": eastern(human.isoformat()), "auto_closed": closed_by_bot,
    }


# ---------- Reading the existing tracker ----------

def rows_by_header(ws) -> list[dict]:
    header = [c.value for c in ws[1]]
    return [dict(zip(header, row)) for row in ws.iter_rows(min_row=2, values_only=True) if row[0] is not None]


def load_existing(path: Path) -> dict:
    """Data, affiliations and last refresh time from an exported tracker."""
    wb = load_workbook(path, data_only=True)
    state = {"prs": {}, "issues": {}, "reviews": [], "contributors": {}, "refreshed": None}
    complete = ("Last human activity (ET)" in [c.value for c in wb["PRs"][1]]
                and "Comments (people)" in [c.value for c in wb["Issues"][1]])
    for row in rows_by_header(wb["PRs"]):
        n = int(row["PR"])
        state["prs"][n] = {
            "number": n, "title": row["Title"], "url": row.get("URL") or f"https://github.com/{REPO}/pull/{n}",
            "author": row["Author"], "created": row["Created (ET)"], "merged": row["Merged (ET)"],
            "closed": row["Closed (ET)"], "state": row["State"], "draft": bool(row["Draft"]),
            "updated": row["Last updated (ET)"], "first_review": row["First review (ET)"],
            "peer_reviews": int(row["Peer reviews"] or 0), "decision": row["Review decision"] or "",
            "human_updated": row.get("Last human activity (ET)"), "auto_closed": bool(row.get("Closed by automation")),
        }
    for row in rows_by_header(wb["Reviews"]):
        n = int(row["PR"])
        state["reviews"].append({
            "pr": n, "url": row.get("URL") or f"https://github.com/{REPO}/pull/{n}", "reviewer": row["Reviewer"],
            "bot": row["Affiliation"] == "Bot", "state": row["State"], "submitted": row["Submitted (ET)"],
        })
    for row in rows_by_header(wb["Issues"]):
        n = int(row["Issue"])
        state["issues"][n] = {
            "number": n, "title": row["Title"], "url": row.get("URL") or f"https://github.com/{REPO}/issues/{n}",
            "author": row["Author"], "created": row["Created (ET)"], "closed": row["Closed (ET)"],
            "state": row["State"], "labels": row["Labels"] or "",
            "comments": int(row.get("Comments (people)") or 0), "updated": row["Last updated (ET)"],
            "human_updated": row.get("Last human activity (ET)"), "auto_closed": bool(row.get("Closed by automation")),
        }
    for row in rows_by_header(wb["Contributors"]):
        state["contributors"][row["Login"]] = (row.get("Affiliation (edit me)") or row.get("Affiliation"), row["Basis"])
    if complete and "_meta" in wb.sheetnames and wb["_meta"]["B1"].value:
        state["refreshed"] = dt.datetime.fromisoformat(str(wb["_meta"]["B1"].value))
        state["automation"] = sorted(filter(None, str(wb["_meta"]["B4"].value or "").split(",")))
    return state


# ---------- Formatting helpers ----------

def font(size: float = 10, bold: bool = False, color: str = INK, italic: bool = False, underline=None) -> Font:
    return Font(name=FONT, size=size, bold=bold, color=color, italic=italic, underline=underline)


def header_row(ws, row: int, labels: list[str], start_col: int = 1) -> None:
    for j, label in enumerate(labels, start=start_col):
        cell = ws.cell(row=row, column=j, value=label)
        cell.font = font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def link(cell, number: int, url: str) -> None:
    cell.value = number
    cell.hyperlink = url
    cell.font = font(color=ACCENT, underline="single")


def widths(ws, spec: dict[str, float]) -> None:
    for col, width in spec.items():
        ws.column_dimensions[col].width = width


# ---------- Workbook ----------

def build(existing: Path | None, out: Path) -> None:
    aff = Affiliations.load(HERE / "contributors.json")
    now = dt.datetime.now(UTC)
    state = load_existing(existing) if existing else {
        "prs": {}, "issues": {}, "reviews": [], "contributors": {}, "refreshed": None}
    sheet_bots = {login for login, (affiliation_value, _) in state["contributors"].items() if affiliation_value == "Bot"}
    AUTOMATION.update(sheet_bots)
    if sorted(AUTOMATION) != state.get("automation"):
        state["refreshed"] = None
    since = state["refreshed"] - REFETCH_OVERLAP if state["refreshed"] else None

    typenames: dict[str, bool] = {}
    pr_nodes = fetch_updated("pullRequests", PR_NODE, since)
    for node in pr_nodes:
        record, reviews = pr_record(node)
        state["prs"][record["number"]] = record
        state["reviews"] = [r for r in state["reviews"] if r["pr"] != record["number"]] + reviews
        typenames[record["author"]] = author_of(node)[1]
        for r in reviews:
            typenames[r["reviewer"]] = r["bot"]
    issue_nodes = fetch_updated("issues", ISSUE_NODE, since)
    for node in issue_nodes:
        record = issue_record(node)
        state["issues"][record["number"]] = record
        typenames[record["author"]] = author_of(node)[1]

    prs = [state["prs"][n] for n in sorted(state["prs"])]
    issues = [state["issues"][n] for n in sorted(state["issues"])]
    reviews = sorted(state["reviews"], key=lambda r: (r["submitted"], r["pr"], r["reviewer"]))

    # Contributors: every affiliation already in the Sheet is kept (people edit them there);
    # new logins get the automatic rule. Basis says which applied.
    labels = {"da": "Digital Asset", "cf": "Canton Foundation", "ext": "External", "bot": "Bot"}

    def by_rule(name: str, is_bot: bool) -> tuple[str, str]:
        affiliation_value = labels[aff.of({"login": name, "__typename": "Bot" if is_bot else "User"})]
        if affiliation_value == "Bot":
            return affiliation_value, "bot account"
        if name in aff.da or name in aff.cf:
            return affiliation_value, "contributors.json"
        if looks_like_da(name):
            return affiliation_value, "login has a -da / DA marker"
        return affiliation_value, "not mapped: default external"

    contributors = {}
    seen = {p["author"] for p in prs} | {i["author"] for i in issues} | {r["reviewer"] for r in reviews}
    for name in seen | state["contributors"].keys():
        old = state["contributors"].get(name)
        was_bot = typenames.get(name, bool(old and old[1] == "bot account"))
        rule = by_rule(name, was_bot)
        if old is None or old[0] == rule[0]:
            contributors[name] = rule
        else:
            contributors[name] = (old[0], "set in the Sheet")

    wb = Workbook()
    # Cells the report formulas spill into have no formatting of their own; make Arial the default.
    wb._named_styles["Normal"].font = Font(name=FONT, size=10)
    wb.active.title = "Overview"
    for title in ("Activity", "People", "Open work", "Contributors", "PRs", "Reviews", "Issues", "About", "_meta"):
        wb.create_sheet(title)
    contrib, pr_ws, rev_ws, iss_ws, meta = (wb[t] for t in ("Contributors", "PRs", "Reviews", "Issues", "_meta"))

    p_last, r_last, i_last = len(prs) + 1, max(len(reviews) + 1, 2), len(issues) + 1
    c_rows = sorted(contributors.items(), key=lambda kv: kv[0].lower())
    c_last = len(c_rows) + 1

    def affiliation(login_cell: str) -> str:
        return (f'=IFERROR(INDEX(Contributors!$B$2:$B${c_last},'
                f'MATCH({login_cell},Contributors!$A$2:$A${c_last},0)),"External")')

    # --- PRs ---
    header_row(pr_ws, 1, ["PR", "Title", "Author", "Affiliation", "Author type", "Created (ET)", "Merged (ET)",
                          "Closed (ET)", "State", "Draft", "Last updated (ET)", "First review (ET)",
                          "Hours to first review", "Hours open to merge", "Peer reviews", "Review decision", "URL",
                          "Last human activity (ET)", "Closed by automation"])
    for i, p in enumerate(prs, start=2):
        link(pr_ws.cell(row=i, column=1), p["number"], p["url"])
        pr_ws.cell(row=i, column=2, value=p["title"])
        pr_ws.cell(row=i, column=3, value=p["author"])
        pr_ws.cell(row=i, column=4, value=affiliation(f"C{i}"))
        pr_ws.cell(row=i, column=5, value=f'=IF(D{i}="Bot","Bot","Person")')
        for col, key in ((6, "created"), (7, "merged"), (8, "closed"), (11, "updated"), (12, "first_review")):
            pr_ws.cell(row=i, column=col, value=p[key]).number_format = DATE_FMT
        pr_ws.cell(row=i, column=9, value=p["state"])
        pr_ws.cell(row=i, column=10, value=p["draft"])
        pr_ws.cell(row=i, column=13, value=f'=IF(L{i}="","",(L{i}-F{i})*24)').number_format = "0.0"
        pr_ws.cell(row=i, column=14, value=f'=IF(G{i}="","",(G{i}-F{i})*24)').number_format = "0.0"
        pr_ws.cell(row=i, column=15, value=p["peer_reviews"])
        pr_ws.cell(row=i, column=16, value=p["decision"])
        pr_ws.cell(row=i, column=17, value=p["url"])
        pr_ws.cell(row=i, column=18, value=p["human_updated"]).number_format = DATE_FMT
        pr_ws.cell(row=i, column=19, value=p["auto_closed"])
    pr_ws.freeze_panes = "B2"
    pr_ws.auto_filter.ref = f"A1:S{p_last}"
    widths(pr_ws, {"A": 8, "B": 50, "C": 22, "D": 18, "E": 11, "F": 16, "G": 16, "H": 16, "I": 9, "J": 7,
                   "K": 16, "L": 16, "M": 11, "N": 11, "O": 9, "P": 18, "Q": 12, "R": 16, "S": 11})

    # --- Reviews (authors reviewing their own PR are excluded) ---
    header_row(rev_ws, 1, ["PR", "Reviewer", "Affiliation", "State", "Submitted (ET)",
                           "First by this reviewer on this PR", "URL"])
    seen_pairs: set[tuple[int, str]] = set()
    for i, r in enumerate(reviews, start=2):
        link(rev_ws.cell(row=i, column=1), r["pr"], r["url"])
        rev_ws.cell(row=i, column=2, value=r["reviewer"])
        rev_ws.cell(row=i, column=3, value=affiliation(f"B{i}"))
        rev_ws.cell(row=i, column=4, value=r["state"])
        rev_ws.cell(row=i, column=5, value=r["submitted"]).number_format = DATE_FMT
        rev_ws.cell(row=i, column=6, value=(r["pr"], r["reviewer"]) not in seen_pairs)
        rev_ws.cell(row=i, column=7, value=r["url"])
        seen_pairs.add((r["pr"], r["reviewer"]))
    rev_ws.freeze_panes = "A2"
    rev_ws.auto_filter.ref = f"A1:G{r_last}"
    widths(rev_ws, {"A": 8, "B": 24, "C": 18, "D": 18, "E": 16, "F": 14, "G": 12})

    # --- Issues ---
    header_row(iss_ws, 1, ["Issue", "Title", "Author", "Affiliation", "Created (ET)", "Closed (ET)", "State",
                           "Labels", "Comments (people)", "Last updated (ET)", "URL", "Last human activity (ET)",
                           "Closed by automation", "Topic labels"])
    for i, n in enumerate(issues, start=2):
        link(iss_ws.cell(row=i, column=1), n["number"], n["url"])
        iss_ws.cell(row=i, column=2, value=n["title"])
        iss_ws.cell(row=i, column=3, value=n["author"])
        iss_ws.cell(row=i, column=4, value=affiliation(f"C{i}"))
        for col, key in ((5, "created"), (6, "closed"), (10, "updated")):
            iss_ws.cell(row=i, column=col, value=n[key]).number_format = DATE_FMT
        iss_ws.cell(row=i, column=7, value=n["state"])
        iss_ws.cell(row=i, column=8, value=n["labels"])
        iss_ws.cell(row=i, column=9, value=n["comments"])
        iss_ws.cell(row=i, column=11, value=n["url"])
        iss_ws.cell(row=i, column=12, value=n["human_updated"]).number_format = DATE_FMT
        iss_ws.cell(row=i, column=13, value=n["auto_closed"])
        # Labels other than the follow-up automation's status/* labels.
        iss_ws.cell(row=i, column=14, value=", ".join(
            lab for lab in (x.strip() for x in n["labels"].split(",")) if lab and not lab.startswith("status/")))
    iss_ws.freeze_panes = "B2"
    iss_ws.auto_filter.ref = f"A1:N{i_last}"
    widths(iss_ws, {"A": 8, "B": 50, "C": 22, "D": 18, "E": 16, "F": 16, "G": 9, "H": 24, "I": 10, "J": 16,
                    "K": 12, "L": 16, "M": 11, "N": 22})

    # --- Contributors: column B is the one place people edit ---
    header_row(contrib, 1, ["Login", "Affiliation (edit me)", "Basis", "PRs opened (all time)",
                            "PRs reviewed (all time)", "Issues opened (all time)"])
    for i, (name, (affiliation_value, basis)) in enumerate(c_rows, start=2):
        contrib.cell(row=i, column=1, value=name)
        cell = contrib.cell(row=i, column=2, value=affiliation_value)
        cell.font = font(color="0000FF")
        cell.fill = INPUT_FILL
        contrib.cell(row=i, column=3, value=basis)
        contrib.cell(row=i, column=4, value=f"=COUNTIF(PRs!$C$2:$C${p_last},$A{i})")
        contrib.cell(row=i, column=5, value=f'=COUNTIFS(Reviews!$B$2:$B${r_last},$A{i},Reviews!$F$2:$F${r_last},TRUE)')
        contrib.cell(row=i, column=6, value=f"=COUNTIF(Issues!$C$2:$C${i_last},$A{i})")
    contrib.freeze_panes = "B2"
    contrib.auto_filter.ref = f"A1:F{c_last}"
    widths(contrib, {"A": 28, "B": 20, "C": 30, "D": 14, "E": 14, "F": 14})
    validation = DataValidation(type="list", formula1='"Digital Asset,Canton Foundation,External,Bot"')
    contrib.add_data_validation(validation)
    validation.add(f"B2:B{c_last + 200}")

    # --- _meta (hidden): refresh time ---
    refreshed_et = now.astimezone(EASTERN).replace(tzinfo=None, microsecond=0)
    meta["A1"], meta["B1"] = "last_refresh_utc", now.replace(microsecond=0).isoformat()
    meta["A2"], meta["B2"] = "as_of_et", refreshed_et
    meta["B2"].number_format = DATE_FMT
    meta["A4"], meta["B4"] = "automation_logins", ",".join(sorted(AUTOMATION))
    meta.sheet_state = "hidden"

    add_reports(wb, Ranges(p_last=p_last, r_last=r_last, i_last=i_last, c_last=c_last))
    build_about(wb["About"])

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.font.name != FONT:
                    cell.font = font(size=cell.font.size or 10, bold=cell.font.bold, italic=cell.font.italic)
    wb.active = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)

    expected = expected_default_view(prs, issues, reviews, contributors, refreshed_et)
    out.with_suffix(".expected.json").write_text(json.dumps(expected, indent=2))
    print(json.dumps({"out": str(out), "prs": len(prs), "issues": len(issues), "reviews": len(reviews),
                      "fetched_prs": len(pr_nodes), "fetched_issues": len(issue_nodes),
                      "new_logins": sorted(seen - state["contributors"].keys()),
                      "since": since.isoformat() if since else None, "expected": expected}))


def expected_default_view(prs, issues, reviews, contributors, asof: dt.datetime) -> dict:
    """The Activity tab's default view (Last week, Everyone), computed without the spreadsheet."""
    day = asof.date() - dt.timedelta(days=asof.weekday())
    end = dt.datetime.combine(day, CUTOFF)
    if end > asof:
        end -= dt.timedelta(days=7)
    start = end - dt.timedelta(days=7)
    person = lambda login: contributors.get(login, ("External",))[0] != "Bot"  # noqa: E731
    within = lambda t: t is not None and start <= t < end  # noqa: E731
    first_pairs, seen = [], set()
    for r in reviews:
        if (r["pr"], r["reviewer"]) not in seen:
            first_pairs.append(r)
        seen.add((r["pr"], r["reviewer"]))
    return {
        "PRs opened": sum(within(p["created"]) and person(p["author"]) for p in prs),
        "PRs merged": sum(within(p["merged"]) and person(p["author"]) for p in prs),
        "PRs closed without merging": sum(within(p["closed"]) and not p["merged"] and person(p["author"]) for p in prs),
        "PRs reviewed (reviewer–PR pairs)": sum(within(r["submitted"]) and person(r["reviewer"]) for r in first_pairs),
        "Issues opened": sum(within(i["created"]) and person(i["author"]) for i in issues),
        "Issues closed": sum(within(i["closed"]) and person(i["author"]) for i in issues),
        # Open work tab, not tied to the period: untouched by people for 30+ days.
        "Open PRs untouched 30+ days": sum(p["state"] == "OPEN" and not p["draft"] and person(p["author"])
                                           and p["human_updated"] < asof - dt.timedelta(days=30) for p in prs),
        "Open issues untouched 30+ days": sum(i["state"] == "OPEN" and person(i["author"])
                                              and i["human_updated"] < asof - dt.timedelta(days=30) for i in issues),
        "period": [start.isoformat(), end.isoformat()],
    }


def build_about(ws) -> None:
    lines = [
        ("cf-docs contribution tracker", "title"),
        (f"Pull requests, issues and reviews from github.com/{REPO}.", ""),
        ("", ""),
        ("Reports", "h"),
        ("Overview: last week's headline numbers and trend charts for the last 26 weeks and every month. It has "
         "no filters, so it looks the same for everyone.", ""),
        ("The other report tabs have yellow dropdowns. They are shared: changing one changes the view for everyone "
         "with the Sheet open, and each daily refresh sets them back to their defaults.", ""),
        ("Activity: totals and a trend for any period, compared with the period before. Choose the period, how to "
         "group the trend (week, month or quarter) and an affiliation.", ""),
        ("People: who opened, merged and reviewed PRs and opened issues in a period, by person and by affiliation.", ""),
        ("Open work: open pull requests or issues right now, filtered by affiliation, days untouched and drafts, "
         "with links to GitHub.", ""),
        ("", ""),
        ("Data", "h"),
        ("Contributors: every GitHub login and its affiliation. Change column B (Digital Asset, Canton Foundation, "
         "External or Bot) and every report updates. These edits are kept when the data refreshes.", ""),
        ("PRs / Reviews / Issues: one row per item, numbers linked to GitHub. Use the column filters to find the "
         "items behind any figure.", ""),
        ("", ""),
        ("Definitions", "h"),
        ("Times are US Eastern. Weeks run Monday 12:00 to Monday 12:00. A period includes its start and excludes "
         "its end (Custom includes the end date).", ""),
        ("Everyone means everyone except bots. Affiliation filters by the author of the PR or issue, or by the "
         "reviewer for reviews.", ""),
        ("PRs reviewed counts each reviewer once per PR, in the period of their first review on it.", ""),
        ("Untouched means no comment, commit, review, label or other change by a person. Bots, including the "
         "follow-up automation that labels, nudges and closes stale items, do not count. Draft PRs are left out of "
         "staleness unless you include them.", ""),
        ("Comments on issues count only comments from people. Topic labels are labels other than the automation's "
         "status/ labels. Closed counts say how many closures the automation made.", ""),
        ("", ""),
        ("Refresh", "h"),
        ("Every morning the latest GitHub activity is added. Affiliations edited on the Contributors tab are kept "
         "(Basis then says \"set in the Sheet\"); other edits are not.", ""),
    ]
    for r, (text, kind) in enumerate(lines, start=1):
        cell = ws.cell(row=r, column=1, value=text)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        cell.font = font(16, bold=True) if kind == "title" else font(12, bold=True) if kind == "h" else font()
    ws.column_dimensions["A"].width = 110


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="existing", type=Path, help="current tracker exported as .xlsx")
    parser.add_argument("--out", type=Path, default=HERE / "tracker" / "cf-docs-tracker.xlsx")
    args = parser.parse_args()
    build(args.existing, args.out)


if __name__ == "__main__":
    main()
