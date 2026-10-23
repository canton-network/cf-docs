#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys
from typing import TypedDict
import urllib.request

from canton_release_reference import USER_AGENT, github_api_json
from docs_env import ensure_repo_direnv
from generate_canton_metrics_reference import mdx_inline


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    REPO_ROOT / "docs-main" / "global-synchronizer" / "reference" / "metrics-reference.mdx"
)
SPLICE_REPO = "canton-network/splice"
# Splice generates this page at docs-build time (apps/metrics-docs, MetricsDocs.scala) and
# gitignores it, so the published GitHub Pages build of main is the only public copy.
SOURCE_PATH = "docs/src/deployment/observability/metrics_reference.rst"
DEFAULT_SOURCE_URL = (
    "https://canton-network.github.io/splice/_sources/"
    "deployment/observability/metrics_reference.rst.txt"
)
GENERATED_START = "{/* GENERATED_SPLICE_METRICS_START */}"
GENERATED_END = "{/* GENERATED_SPLICE_METRICS_END */}"
SECTIONS = (
    ("common", "Common Metrics"),
    ("validator", "Validator Metrics"),
    ("sv", "SV Metrics"),
    ("scan", "Scan Metrics"),
)
FIELDS = ("Summary", "Description", "Type", "Qualification")
FIELD_RE = re.compile(r"^\* \*\*(?P<field>[A-Za-z]+)\*\*: ?(?P<value>.*)$")


class MetricItem(TypedDict):
    name: str
    summary: str
    description: str
    type: str
    qualification: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Splice Metrics reference page from Splice's published docs build."
    )
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument(
        "--source-file",
        type=Path,
        help="Use a local copy of the generated metrics_reference.rst instead of downloading it.",
    )
    parser.add_argument(
        "--source-commit",
        help="Splice commit the source was built from. Defaults to the latest github-pages deployment.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read().decode("utf-8")


def latest_pages_commit() -> str:
    deployments = github_api_json(
        f"repos/{SPLICE_REPO}/deployments?environment=github-pages&per_page=1"
    )
    if not isinstance(deployments, list) or not deployments:
        raise ValueError(f"{SPLICE_REPO} has no github-pages deployments")
    sha = deployments[0].get("sha")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError(f"Unexpected github-pages deployment commit {sha!r}")
    return sha


def underline(line: str, char: str) -> bool:
    return len(line) >= 3 and set(line) == {char}


def parse_metrics_rst(text: str) -> dict[str, list[MetricItem]]:
    """Parse the RST rendered by Splice's MetricsDocs.render()."""
    headings = {heading: key for key, heading in SECTIONS}
    sections: dict[str, list[MetricItem]] = {}
    lines = text.splitlines()
    section: str | None = None
    current: dict[str, str] | None = None

    def finish() -> None:
        if current is None:
            return
        missing = [field for field in FIELDS if field.lower() not in current]
        if missing:
            raise ValueError(f"Splice metric {current['name']!r} is missing {missing}")
        assert section is not None
        sections[section].append(
            MetricItem(
                name=current["name"],
                summary=current["summary"],
                description=current["description"],
                type=current["type"],
                qualification=current["qualification"],
            )
        )

    for index, line in enumerate(lines):
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if underline(following, "+") and len(following) == len(line):
            finish()
            current = None
            if line not in headings:
                raise ValueError(f"Unexpected Splice metrics section {line!r}")
            section = headings[line]
            sections[section] = []
        elif underline(following, "^") and len(following) == len(line):
            finish()
            if section is None:
                raise ValueError(f"Splice metric {line!r} appears before any section")
            current = {"name": line}
        elif current is not None and (match := FIELD_RE.match(line)):
            field = match["field"]
            if field not in FIELDS:
                raise ValueError(f"Splice metric {current['name']!r} has unknown field {field!r}")
            current[field.lower()] = match["value"]
    finish()

    for key, heading in SECTIONS:
        if not sections.get(key):
            raise ValueError(f"Splice metrics source has no {heading}")
    return sections


def render_metric(item: MetricItem) -> list[str]:
    return [
        f"### {mdx_inline(item['name'])}",
        "",
        f"> - **Summary**: {mdx_inline(item['summary'])}".rstrip(),
        f"> - **Description**: {mdx_inline(item['description'])}".rstrip(),
        f"> - **Type**: {mdx_inline(item['type'])}".rstrip(),
        f"> - **Qualification**: {mdx_inline(item['qualification'])}".rstrip(),
    ]


def render_generated_block(
    sections: dict[str, list[MetricItem]], *, commit: str, digest: str
) -> str:
    counts = " ".join(
        f'{key}_metric_count="{len(sections[key])}"' for key, _ in SECTIONS
    )
    lines = [
        GENERATED_START,
        "",
        (
            "{/* GENERATED_FROM "
            f'source="{SPLICE_REPO}" path="{SOURCE_PATH}" ref="{commit}" '
            f'digest="sha256:{digest}" {counts} */}}'
        ),
    ]
    for key, heading in SECTIONS:
        lines.extend(["", f"## {heading}"])
        for item in sections[key]:
            lines.append("")
            lines.extend(render_metric(item))
    lines.extend(["", GENERATED_END])
    return "\n".join(lines)


def replace_generated_block(page: str, block: str) -> str:
    start = page.find(GENERATED_START)
    end = page.find(GENERATED_END, start)
    if start == -1 or end == -1:
        raise ValueError(
            f"Splice metrics page is missing its {GENERATED_START} and {GENERATED_END} markers"
        )
    end += len(GENERATED_END)
    return page[:start].rstrip() + "\n\n" + block + "\n\n" + page[end:].lstrip()


def main() -> int:
    ensure_repo_direnv(
        repo_root=REPO_ROOT, script_path=Path(__file__).resolve(), argv=sys.argv[1:]
    )
    args = parse_args()
    commit = args.source_commit or latest_pages_commit()
    if args.source_file:
        text = args.source_file.read_text(encoding="utf-8")
    else:
        text = fetch_text(args.source_url)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    sections = parse_metrics_rst(text)
    page = args.output.read_text(encoding="utf-8")
    args.output.write_text(
        replace_generated_block(
            page, render_generated_block(sections, commit=commit, digest=digest)
        ),
        encoding="utf-8",
    )
    print(f"Generated {args.output} from {SPLICE_REPO}@{commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
