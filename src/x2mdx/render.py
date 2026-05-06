"""Render shared output-side data structures into MDX."""

from __future__ import annotations

from pathlib import Path

from x2mdx.output import Block, BulletList, Heading, Page, Paragraph, RawMarkdown, Table


def frontmatter_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_block(block: Block) -> str:
    if isinstance(block, Heading):
        return f"{'#' * block.level} {block.text}\n"
    if isinstance(block, Paragraph):
        return f"{block.text}\n"
    if isinstance(block, BulletList):
        return "\n".join(f"- {item}" for item in block.items) + "\n"
    if isinstance(block, Table):
        lines = [
            "| " + " | ".join(block.headers) + " |",
            "| " + " | ".join("---" for _ in block.headers) + " |",
        ]
        lines.extend("| " + " | ".join(row) + " |" for row in block.rows)
        return "\n".join(lines) + "\n"
    if isinstance(block, RawMarkdown):
        return block.text.rstrip() + "\n"
    raise TypeError(f"Unsupported block type: {type(block)!r}")


def render_page(page: Page) -> str:
    lines = ["---", f'title: "{frontmatter_escape(page.title)}"']
    if page.description is not None:
        lines.append(f'description: "{frontmatter_escape(page.description)}"')
    lines.extend(["---", ""])

    body_parts = [render_block(block).rstrip() for block in page.blocks]
    body = "\n\n".join(part for part in body_parts if part)
    if body:
        lines.append(body)
    return "\n".join(lines).rstrip() + "\n"


def write_page(page: Page, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_page(page), encoding="utf-8")
    return target


def write_pages(pages: list[Page], root: Path) -> list[Path]:
    written: list[Path] = []
    for page in pages:
        written.append(write_page(page, root / page.path))
    return written
