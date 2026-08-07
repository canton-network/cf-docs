from __future__ import annotations

import re

from .model import (
    DirectiveAttribute,
    DirectiveSyntaxRule,
    ElseTag,
    IfVersionTag,
    SnippetTag,
    Span,
)

SNIPPET_TAG_RE = re.compile(
    r"<(?P<closing>/)?Snippet\b"
    r"(?P<body>(?:[^\"'>]|\"[^\"]*\"|'[^']*')*?)"
    r"(?P<self_closing>/)?>",
    re.DOTALL,
)
ATTRIBUTE_RE = re.compile(
    r"\s+(?P<name>[A-Za-z][A-Za-z0-9]*)\s*=\s*"
    r"(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|\{(?P<number>[0-9]+)\})"
)
CONDITION_TAG_RE = re.compile(
    r"<(?P<closing>/)?(?P<name>IfVersion|Else)\b"
    r"(?P<body>(?:[^\"'>]|\"[^\"]*\"|'[^']*')*?)"
    r"(?P<self_closing>/)?>",
    re.DOTALL,
)


class DirectiveSyntaxError(ValueError):
    def __init__(
        self, rule: DirectiveSyntaxRule, message: str, span: Span
    ) -> None:
        self.rule = rule
        self.span = span
        super().__init__(message)


def _masked_source(text: str) -> str:
    """Mask Markdown code and MDX comments while preserving source offsets."""

    chars = list(text)
    ranges: list[tuple[int, int]] = []
    fence_start: int | None = None
    fence_character: str | None = None
    fence_length = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip(" \t")
        fence = re.match(r"(?P<fence>`{3,}|~{3,})", stripped)
        if fence_start is None and fence:
            marker = fence.group("fence")
            fence_start = offset
            fence_character = marker[0]
            fence_length = len(marker)
        elif fence_start is not None and fence:
            marker = fence.group("fence")
            remainder = stripped[len(marker) :].strip()
            if (
                marker[0] == fence_character
                and len(marker) >= fence_length
                and not remainder
            ):
                ranges.append((fence_start, offset + len(line)))
                fence_start = None
                fence_character = None
                fence_length = 0
        offset += len(line)
    if fence_start is not None:
        ranges.append((fence_start, len(text)))
    ranges.extend(
        (match.start(), match.end())
        for match in re.finditer(r"(?s)\{?/\*.*?\*/\}?", text)
    )
    for start, end in ranges:
        for index in range(start, end):
            if chars[index] != "\n":
                chars[index] = " "

    masked = "".join(chars)
    offset = 0
    for line in masked.splitlines(keepends=True):
        index = 0
        while index < len(line):
            if line[index] != "`":
                index += 1
                continue
            run_end = index + 1
            while run_end < len(line) and line[run_end] == "`":
                run_end += 1
            marker = line[index:run_end]
            close = line.find(marker, run_end)
            if close < 0:
                index = run_end
                continue
            for position in range(offset + index, offset + close + len(marker)):
                if chars[position] != "\n":
                    chars[position] = " "
            index = close + len(marker)
        offset += len(line)
    return "".join(chars)


def _span(text: str, start: int, end: int) -> Span:
    line_start = text.rfind("\n", 0, start) + 1
    return Span(
        start=start,
        end=end,
        line=text.count("\n", 0, start) + 1,
        column=start - line_start + 1,
    )


def _parse_attributes(
    body: str, span: Span, *, tag_name: str
) -> tuple[DirectiveAttribute, ...]:
    attributes: list[DirectiveAttribute] = []
    names: set[str] = set()
    position = 0
    for match in ATTRIBUTE_RE.finditer(body):
        malformed = body[position : match.start()].strip()
        if malformed:
            raise DirectiveSyntaxError(
                DirectiveSyntaxRule.MALFORMED_ATTRIBUTES,
                f"Malformed {tag_name} attributes near {malformed!r}",
                span,
            )
        name = match.group("name")
        if name in names:
            raise DirectiveSyntaxError(
                DirectiveSyntaxRule.DUPLICATE_ATTRIBUTE,
                f"Duplicate {tag_name} attribute {name!r}",
                span,
            )
        names.add(name)
        if match.group("number") is not None:
            value: str | int = int(match.group("number"))
        elif match.group("double") is not None:
            value = match.group("double")
        else:
            value = match.group("single")
        attributes.append(DirectiveAttribute(name=name, value=value))
        position = match.end()
    malformed = body[position:].strip()
    if malformed:
        raise DirectiveSyntaxError(
            DirectiveSyntaxRule.MALFORMED_ATTRIBUTES,
            f"Malformed {tag_name} attributes near {malformed!r}",
            span,
        )
    return tuple(attributes)


def parse_snippet_tags(text: str) -> tuple[SnippetTag, ...]:
    """Parse well-formed Snippet tags without interpreting their attributes."""

    snippets: list[SnippetTag] = []
    masked = _masked_source(text)
    for match in SNIPPET_TAG_RE.finditer(masked):
        span = _span(text, match.start(), match.end())
        if match.group("closing") or not match.group("self_closing"):
            raise DirectiveSyntaxError(
                DirectiveSyntaxRule.SNIPPET_NOT_SELF_CLOSING,
                "Snippet must be self-closing",
                span,
            )
        snippets.append(
            SnippetTag(
                attributes=_parse_attributes(
                    match.group("body"), span, tag_name="Snippet"
                ),
                span=span,
            )
        )
    return tuple(snippets)


def parse_if_version_tags(text: str) -> tuple[IfVersionTag | ElseTag, ...]:
    """Parse conditional tags without validating their nesting or attributes."""

    tags: list[IfVersionTag | ElseTag] = []
    masked = _masked_source(text)
    for match in CONDITION_TAG_RE.finditer(masked):
        span = _span(text, match.start(), match.end())
        name = match.group("name")
        closing = bool(match.group("closing"))
        self_closing = bool(match.group("self_closing"))
        body = match.group("body")
        if self_closing:
            raise DirectiveSyntaxError(
                (
                    DirectiveSyntaxRule.ELSE_SELF_CLOSING
                    if name == "Else"
                    else DirectiveSyntaxRule.IF_VERSION_SELF_CLOSING
                ),
                f"{name} cannot be self-closing",
                span,
            )
        if closing and body.strip():
            raise DirectiveSyntaxError(
                DirectiveSyntaxRule.CLOSING_ATTRIBUTES,
                f"Closing {name} tag cannot have attributes",
                span,
            )
        if name == "Else":
            if body.strip():
                raise DirectiveSyntaxError(
                    DirectiveSyntaxRule.ELSE_ATTRIBUTES,
                    "Else cannot have attributes",
                    span,
                )
            tags.append(ElseTag(span=span, closing=closing))
            continue
        attributes = (
            ()
            if closing
            else _parse_attributes(body, span, tag_name="IfVersion")
        )
        tags.append(
            IfVersionTag(attributes=attributes, span=span, closing=closing)
        )
    return tuple(tags)
