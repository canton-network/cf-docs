from __future__ import annotations

from pathlib import Path

import pytest

from scripts.snippets.compiler import (
    GeneratedOutputDrift,
    assert_generated_output,
    compile_page,
    generated_path,
    write_generated_output,
)
from scripts.snippets.model import SourceReference
from scripts.snippets.source import ResolvedSource


REPOSITORY = "canton-network/splice"
COMMIT = "2c941ea9e834d7602d388f3271c0f864025ea756"
REPOSITORIES = {
    REPOSITORY: {
        "url": f"https://github.com/{REPOSITORY}",
        "defaultBranch": "main",
    }
}
PAGE = Path("docs-main/validator.source.mdx")


class FakeResolver:
    def __init__(self) -> None:
        self.references: list[SourceReference] = []

    def resolve(
        self, reference: SourceReference, *, production: bool = False
    ) -> ResolvedSource:
        self.references.append(reference)
        content = (
            b"# START\nnew: true\n# END\n"
            if reference.pull_request
            else b"# START\nexisting: true\n# END\n"
        )
        return ResolvedSource(reference, COMMIT, content)


def source_page() -> str:
    return f"""---
title: Validator
---

<IfVersion
  repository="https://github.com/{REPOSITORY}"
  containsPullRequest={{6123}}
>
Use the new setting.

<Snippet
  source="https://github.com/{REPOSITORY}/pull/6123"
  path="apps/validator-values.yaml"
  startAfter="START"
  endBefore="END"
  language="yaml"
/>
<Else>
Use the existing setting.

<Snippet
  source="https://github.com/{REPOSITORY}/blob/{COMMIT}/apps/validator-values.yaml"
  startAfter="START"
  endBefore="END"
  language="yaml"
/>
</Else>
</IfVersion>
"""


def compile(contains: bool) -> tuple[str, FakeResolver]:
    resolver = FakeResolver()
    rendered = compile_page(
        source_page(),
        page_path=PAGE,
        repositories=REPOSITORIES,
        source_resolver=resolver,  # type: ignore[arg-type]
        condition_contains=lambda _: contains,
        production=True,
    )
    return rendered, resolver


def test_compiles_only_new_prose_and_candidate_when_release_contains_change() -> None:
    rendered, resolver = compile(True)

    assert "Use the new setting." in rendered
    assert "new: true" in rendered
    assert "Use the existing setting." not in rendered
    assert "existing: true" not in rendered
    assert len(resolver.references) == 1
    assert resolver.references[0].pull_request == 6123
    assert "<IfVersion" not in rendered
    assert "<Snippet" not in rendered
    assert "snippet-source: https://github.com/canton-network/splice/blob/" in rendered


def test_compiles_only_existing_prose_and_immutable_snippet_otherwise() -> None:
    rendered, resolver = compile(False)

    assert "Use the existing setting." in rendered
    assert "existing: true" in rendered
    assert "Use the new setting." not in rendered
    assert "new: true" not in rendered
    assert len(resolver.references) == 1
    assert resolver.references[0].commit == COMMIT


def test_uses_a_longer_fence_when_source_contains_backticks() -> None:
    resolver = FakeResolver()
    resolver.resolve = lambda reference, production=False: ResolvedSource(  # type: ignore[method-assign]
        reference, COMMIT, b"const example = `value`;\n```\n"
    )
    page = f'<Snippet source="https://github.com/{REPOSITORY}/blob/{COMMIT}/a.ts" language="typescript" />'

    rendered = compile_page(
        page,
        page_path=PAGE,
        repositories=REPOSITORIES,
        source_resolver=resolver,  # type: ignore[arg-type]
        condition_contains=lambda _: False,
        production=True,
    )

    assert "````typescript\n" in rendered
    assert rendered.rstrip().endswith("````")


def test_generated_output_path_and_drift_check(tmp_path: Path) -> None:
    source = tmp_path / "validator.source.mdx"
    source.write_text("authored", encoding="utf-8")
    assert generated_path(source) == tmp_path / "validator.mdx"

    with pytest.raises(GeneratedOutputDrift, match="missing"):
        assert_generated_output(source, "compiled")

    target = write_generated_output(source, "compiled")
    assert target.read_text(encoding="utf-8") == "compiled"
    assert_generated_output(source, "compiled")

    target.write_text("stale", encoding="utf-8")
    with pytest.raises(GeneratedOutputDrift, match="stale"):
        assert_generated_output(source, "compiled")
