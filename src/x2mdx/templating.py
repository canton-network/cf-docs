"""Shared Jinja-based markdown templating helpers."""

from __future__ import annotations

import html
import re
from functools import lru_cache
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined

from x2mdx.output import Page, RawMarkdown


def heading(level: int, text: str) -> str:
    return f"{'#' * level} {text}"


def paragraph(text: str) -> str:
    return text


def bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def code_block(language: str, body: str) -> str:
    return f"```{language}\n{body}\n```"


def anchor(anchor_id: str) -> str:
    return f'<a id="{anchor_id}"></a>'


def admonition(kind: str, body: str) -> str:
    return f"<{kind}>\n{body}\n</{kind}>"


def escape_html(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def escape_mdx_html_text(value: Any) -> str:
    escaped = escape_html(value)
    return escaped.replace("{", "&#123;").replace("}", "&#125;")


def escape_js_template_literal(value: Any) -> str:
    return ("" if value is None else str(value)).replace("`", "\\`").replace("${", "\\${")


def inline_text(value: Any) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def accordion_list(title: str, items: list[str]) -> str:
    lines = ["<AccordionGroup>", f'<Accordion title="{title}">']
    lines.extend(f"- {item}" for item in items)
    lines.extend(["</Accordion>", "</AccordionGroup>"])
    return "\n".join(lines)


def render_card_group(cards: list[dict[str, Any]], cols: int = 2) -> str:
    lines = [f"<CardGroup cols={{{cols}}}>"]
    for card in cards:
        lines.append(f'<Card title="{card["title"]}">')
        body = str(card["body"]).strip("\n")
        if body:
            lines.extend(body.splitlines())
        lines.append("</Card>")
    lines.append("</CardGroup>")
    return "\n".join(lines)


def pretty_json(value: Any) -> str:
    import json

    return json.dumps(value, indent=2)


def compact_version_label(value: Any) -> str:
    text = str(value).strip()
    if not text or text == "-":
        return "-"
    if text.startswith("v"):
        return text
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].*)?", text)
    if match:
        return f"v{match.group(1)}.{match.group(2)}"
    return f"v{text}"


def compact_version_sequence(values: list[Any]) -> str:
    labels = [compact_version_label(value) for value in values if str(value).strip() and str(value).strip() != "-"]
    if not labels:
        return "-"
    if len(labels) == 1:
        return labels[0]
    return f"{labels[-1]} +{len(labels) - 1}"


def render_status_cell(
    *,
    introduced: Any | None = None,
    changed: list[Any] | None = None,
    deprecated: Any | None = None,
    removed: Any | None = None,
) -> str:
    parts: list[str] = []
    introduced_text = str(introduced).strip() if introduced is not None else ""
    deprecated_text = str(deprecated).strip() if deprecated is not None else ""
    removed_text = str(removed).strip() if removed is not None else ""
    if introduced_text and introduced_text != "-":
        parts.append(f"🟢 `{compact_version_label(introduced_text)}`")
    changed_versions: list[str] = []
    for value in changed or []:
        text = str(value).strip()
        if not text or text == "-":
            continue
        if text in {introduced_text, deprecated_text, removed_text}:
            continue
        if text not in changed_versions:
            changed_versions.append(text)
    if changed_versions:
        parts.append(f"🔵 `{compact_version_sequence(changed_versions)}`")
    if deprecated_text and deprecated_text != "-":
        parts.append(f"🟠 `{compact_version_label(deprecated_text)}`")
    if removed_text and removed_text != "-":
        parts.append(f"🔴 `{compact_version_label(removed_text)}`")
    return " ".join(parts) or "-"


def render_status_legend(
    *,
    include_changed: bool = True,
    include_deprecated: bool = True,
    include_removed: bool = True,
) -> str:
    items = ["🟢 Active Since"]
    if include_changed:
        items.append("🔵 Changed")
    if include_deprecated:
        items.append("🟠 Deprecated")
    if include_removed:
        items.append("🔴 Removed")
    return "  ".join(items)


def _finalize(value: Any) -> Any:
    return "" if value is None else value


@lru_cache(maxsize=1)
def template_environment() -> Environment:
    environment = Environment(
        loader=PackageLoader("x2mdx", "templates"),
        autoescape=False,
        keep_trailing_newline=True,
        lstrip_blocks=False,
        trim_blocks=False,
        undefined=StrictUndefined,
        finalize=_finalize,
    )
    environment.globals.update(
        heading=heading,
        paragraph=paragraph,
        bullet_list=bullet_list,
        table=table,
        code_block=code_block,
        anchor=anchor,
        admonition=admonition,
        escape_html=escape_html,
        escape_mdx_html_text=escape_mdx_html_text,
        escape_js_template_literal=escape_js_template_literal,
        inline_text=inline_text,
        accordion_list=accordion_list,
        render_card_group=render_card_group,
        pretty_json=pretty_json,
        compact_version_label=compact_version_label,
        compact_version_sequence=compact_version_sequence,
        render_status_cell=render_status_cell,
        render_status_legend=render_status_legend,
    )
    return environment


def render_template(name: str, /, **context: Any) -> str:
    collapse_blank_lines = bool(context.pop("collapse_blank_lines", True))
    rendered = template_environment().get_template(name).render(**context)
    if collapse_blank_lines:
        rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered.strip()


def markdown_page(
    *,
    path: str,
    title: str,
    description: str | None,
    template_name: str,
    **context: Any,
) -> Page:
    return Page(
        path=path,
        title=title,
        description=description,
        blocks=[RawMarkdown(render_template(template_name, **context))],
    )
