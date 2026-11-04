#!/usr/bin/env python3
"""Fail when an MDX file renders a capitalized JSX component it never declares.

Mintlify renders an undeclared component such as `<KmsParticipantsContext />`
as nothing, so a missing snippet import silently drops content instead of
failing the build. A component counts as declared when the file imports or
exports it, or when it is one of Mintlify's built-in components.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_MAIN = REPO_ROOT / "docs-main"

# Built-in components from https://mintlify.com/docs (Components section) and
# the component registries in @mintlify/common `mdx/componentIds`.
MINTLIFY_COMPONENTS = frozenset(
    {
        "Accordion",
        "AccordionGroup",
        "Badge",
        "Callout",
        "Card",
        "CardGroup",
        "Check",
        "CodeBlock",
        "CodeGroup",
        "Color",
        "Column",
        "Columns",
        "Danger",
        "Expandable",
        "Frame",
        "Icon",
        "Info",
        "Latex",
        "Mermaid",
        "Note",
        "Panel",
        "ParamField",
        "Prompt",
        "RequestExample",
        "ResponseExample",
        "ResponseField",
        "SnippetGroup",
        "Step",
        "Steps",
        "Tab",
        "Tabs",
        "Tile",
        "Tip",
        "Tooltip",
        "Tree",
        "Update",
        "View",
        "Visibility",
        "Warning",
    }
)

FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
FENCE_RE = re.compile(r"^\s*(?:>\s*)*(`{3,}|~{3,})")
JSX_COMMENT_RE = re.compile(r"\{/\*.*?\*/\}", re.DOTALL)
INLINE_CODE_RE = re.compile(r"(`+)(?!`).*?(?<!`)\1")
IMPORT_RE = re.compile(r"^\s*import\s+(?P<clause>.+?)\s+from\s+[\"']", re.MULTILINE)
EXPORT_RE = re.compile(
    r"^\s*export\s+(?:const|let|var|function)\s+(?P<name>[A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
IDENTIFIER_RE = re.compile(r"[A-Za-z_$][\w$]*")
COMPONENT_RE = re.compile(r"(?<!\\)<(?P<name>[A-Z][\w$]*)")


@dataclass(frozen=True)
class UndeclaredComponent:
    path: Path
    line: int
    name: str


def strip_code_and_comments(text: str) -> str:
    """Blank out frontmatter, fenced code, inline code, and JSX comments.

    Line structure is preserved so reported line numbers stay accurate.
    """
    text = FRONTMATTER_RE.sub(lambda match: "\n" * match.group(0).count("\n"), text)
    lines: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        match = FENCE_RE.match(line)
        if fence is not None:
            marker = match.group(1) if match else ""
            if marker[:1] == fence[:1] and len(marker) >= len(fence):
                fence = None
            lines.append("")
            continue
        if match:
            fence = match.group(1)
            lines.append("")
            continue
        lines.append(INLINE_CODE_RE.sub("", line))
    text = "\n".join(lines)
    return JSX_COMMENT_RE.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def declared_names(text: str) -> set[str]:
    names: set[str] = set()
    for match in IMPORT_RE.finditer(text):
        clause = re.sub(r"\b[\w$]+\s+as\s+", "", match.group("clause"))
        names.update(IDENTIFIER_RE.findall(clause))
    names.update(match.group("name") for match in EXPORT_RE.finditer(text))
    return names


def undeclared_components(path: Path) -> list[UndeclaredComponent]:
    text = path.read_text(encoding="utf-8")
    declared = declared_names(text) | MINTLIFY_COMPONENTS
    found: list[UndeclaredComponent] = []
    for line_number, line in enumerate(strip_code_and_comments(text).split("\n"), start=1):
        for match in COMPONENT_RE.finditer(line):
            name = match.group("name")
            if name not in declared:
                found.append(UndeclaredComponent(path, line_number, name))
    return found


def audit(docs_main: Path = DOCS_MAIN) -> list[UndeclaredComponent]:
    found: list[UndeclaredComponent] = []
    for path in sorted(docs_main.rglob("*.mdx")):
        if path.is_file():
            found.extend(undeclared_components(path))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-main", type=Path, default=DOCS_MAIN)
    args = parser.parse_args(argv)
    docs_main = args.docs_main.resolve()
    found = audit(docs_main)
    for item in found:
        print(
            f"{item.path.relative_to(docs_main.parent)}:{item.line}: "
            f"<{item.name}> is neither imported, exported, nor a Mintlify built-in",
            file=sys.stderr,
        )
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
