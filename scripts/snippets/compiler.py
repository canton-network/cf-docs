from __future__ import annotations

import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import IfVersionDirective, SnippetDirective
from .parser import TAG_RE, _masked_source, parse_page
from .source import ResolvedSource, SourceResolver, extract_snippet


class GeneratedOutputDrift(Exception):
    pass


ConditionPredicate = Callable[[IfVersionDirective], bool]


@dataclass(frozen=True)
class CompilationTarget:
    label: str
    condition_contains: ConditionPredicate
    production: bool


def generated_path(source_path: Path) -> Path:
    suffix = ".source.mdx"
    if not source_path.name.endswith(suffix):
        raise ValueError(f"Authored snippet page must end in {suffix}: {source_path}")
    return source_path.with_name(f"{source_path.name.removesuffix(suffix)}.mdx")


def _code_fence(content: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def _provenance(directive: SnippetDirective, source: ResolvedSource) -> str:
    if source.commit:
        encoded_path = urllib.parse.quote(source.reference.path, safe="/")
        return (
            f"https://github.com/{source.reference.repository}/blob/"
            f"{source.commit}/{encoded_path}"
        )
    return (
        f"local://{source.reference.repository}/"
        f"{urllib.parse.quote(source.reference.path, safe='/')}"
    )


def render_snippet(
    directive: SnippetDirective,
    source: ResolvedSource,
    *,
    page_path: Path,
) -> str:
    content = extract_snippet(directive, source)
    fence = _code_fence(content)
    if content and not content.endswith("\n"):
        content += "\n"
    provenance = _provenance(directive, source)
    return (
        f"{{/* snippet-source: {provenance}; "
        f"authored-at: {page_path.as_posix()}:{directive.span.line} */}}\n"
        f"{fence}{directive.language}\n{content}{fence}"
    )


def compile_page(
    text: str,
    *,
    page_path: Path,
    repositories: dict[str, dict[str, Any]],
    source_resolver: SourceResolver,
    condition_contains: ConditionPredicate,
    production: bool,
    allow_local: bool = False,
) -> str:
    return compile_page_variants(
        text,
        page_path=page_path,
        repositories=repositories,
        source_resolver=source_resolver,
        targets=(
            CompilationTarget(
                label="selected release",
                condition_contains=condition_contains,
                production=production,
            ),
        ),
        allow_local=allow_local,
    )


def compile_page_variants(
    text: str,
    *,
    page_path: Path,
    repositories: dict[str, dict[str, Any]],
    source_resolver: SourceResolver,
    targets: tuple[CompilationTarget, ...],
    allow_local: bool = False,
) -> str:
    if not targets:
        raise ValueError("At least one compilation target is required")
    parsed = parse_page(
        text,
        path=page_path,
        repositories=repositories,
        allow_local=allow_local,
    )
    snippets = {directive.span.start: directive for directive in parsed.snippets}
    conditions = {directive.span.start: directive for directive in parsed.conditions}
    masked = _masked_source(text)
    tokens = list(TAG_RE.finditer(masked))

    def condition_block(opening_index: int) -> tuple[int | None, int | None, int]:
        depth = 0
        else_open: int | None = None
        else_close: int | None = None
        for index in range(opening_index, len(tokens)):
            token = tokens[index]
            name = token.group("name")
            closing = bool(token.group("closing"))
            if name == "IfVersion":
                depth += -1 if closing else 1
                if depth == 0:
                    return else_open, else_close, index
            elif name == "Else" and depth == 1:
                if closing:
                    else_close = index
                else:
                    else_open = index
        raise AssertionError("Validated IfVersion has no closing token")

    def selected_branch(
        token: re.Match[str],
        close_token: re.Match[str],
        else_open: int | None,
        else_close: int | None,
        target: CompilationTarget,
        directive: IfVersionDirective,
    ) -> str:
        if target.condition_contains(directive):
            branch_end = (
                tokens[else_open].start()
                if else_open is not None
                else close_token.start()
            )
            return render_range(token.end(), branch_end, target)
        if else_open is not None and else_close is not None:
            return render_range(
                tokens[else_open].end(), tokens[else_close].start(), target
            )
        return ""

    def render_range(
        start: int, end: int, active_target: CompilationTarget | None
    ) -> str:
        output: list[str] = []
        position = start
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token.start() < start:
                index += 1
                continue
            if token.start() >= end:
                break
            name = token.group("name")
            if token.group("closing"):
                index += 1
                continue
            output.append(text[position : token.start()])
            if name == "Snippet":
                directive = snippets[token.start()]
                resolved = source_resolver.resolve(
                    directive.source,
                    production=(active_target or targets[0]).production,
                )
                output.append(render_snippet(directive, resolved, page_path=page_path))
                position = token.end()
                index += 1
                continue
            if name == "IfVersion":
                directive = conditions[token.start()]
                else_open, else_close, close_index = condition_block(index)
                close_token = tokens[close_index]
                if active_target is not None:
                    output.append(
                        selected_branch(
                            token,
                            close_token,
                            else_open,
                            else_close,
                            active_target,
                            directive,
                        )
                    )
                elif len(targets) == 1:
                    output.append(
                        selected_branch(
                            token,
                            close_token,
                            else_open,
                            else_close,
                            targets[0],
                            directive,
                        )
                    )
                else:
                    variants = ["<Tabs>"]
                    for target in targets:
                        label = target.label.replace("&", "&amp;").replace(
                            '"', "&quot;"
                        )
                        variants.append(f'<Tab title="{label}">')
                        variants.append(
                            selected_branch(
                                token,
                                close_token,
                                else_open,
                                else_close,
                                target,
                                directive,
                            )
                        )
                        variants.append("</Tab>")
                    variants.append("</Tabs>")
                    output.append("\n".join(variants))
                position = close_token.end()
                index = close_index + 1
                continue
            # Else tokens are bounded out of recursively selected branch ranges.
            position = token.end()
            index += 1
        output.append(text[position:end])
        return "".join(output)

    compiled = render_range(0, len(text), None)
    header = (
        f"{{/* Generated from {page_path.name}. "
        f"Edit {page_path.name}, then run npm run snippets:generate. */}}\n"
    )
    return header + compiled


def assert_generated_output(source_path: Path, compiled: str) -> None:
    target = generated_path(source_path)
    try:
        actual = target.read_text(encoding="utf-8")
    except OSError as error:
        raise GeneratedOutputDrift(
            f"Generated page is missing for {source_path}: {target}"
        ) from error
    if actual != compiled:
        raise GeneratedOutputDrift(
            f"Generated page is stale for {source_path}: run `npm run snippets:generate -- --page {source_path}`"
        )


def write_generated_output(source_path: Path, compiled: str) -> Path:
    target = generated_path(source_path)
    target.write_text(compiled, encoding="utf-8")
    return target
