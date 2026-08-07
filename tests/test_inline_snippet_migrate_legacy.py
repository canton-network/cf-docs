from __future__ import annotations

from pathlib import Path

from scripts.snippets import migrate_legacy
from scripts.snippets.migrate_legacy import LegacySnippet, SourcePin, declaration


def snippet(entry: dict, substitutions: dict[str, str] | None = None) -> LegacySnippet:
    return LegacySnippet(Path("manifest.json"), substitutions or {}, entry)


def test_translates_line_mapping_to_complete_immutable_declaration() -> None:
    item = snippet(
        {
            "snippetName": "example",
            "sourceRepo": "quickstart",
            "sourceFilepath": "docs/example.rst",
            "location": {"type": "lines", "start": 12, "end": 16},
            "options": {"language": "bash", "normalizeIndent": False},
        }
    )
    pin = SourcePin(
        "quickstart",
        "digital-asset/cn-quickstart",
        "9debe90ba909c6cb69329144a6870624d26cbdc3",
    )

    rendered = declaration(item, pin, "source")

    assert "https://github.com/digital-asset/cn-quickstart/blob/9debe90" in rendered
    assert 'lines="12..16"' in rendered
    assert 'normalize="preserve"' in rendered
    assert 'language="bash"' in rendered


def test_generated_canton_json_is_explicitly_blocked() -> None:
    item = snippet(
        {
            "snippetName": "generated",
            "sourceRepo": "canton",
            "sourceFilepath": "docs-open/target/snippet_json_data/page.json",
            "location": {"type": "jsonIndex", "start": 0, "end": 0},
            "options": {"language": "scala", "transform": "rstjson"},
        }
    )

    assert (
        item.blocked_reason == "generated Canton JSON source is not committed upstream"
    )


def test_declares_legacy_url_substitution_in_the_page() -> None:
    old = "https://old.example/path"
    new = "[current docs](/current)"
    item = snippet(
        {
            "snippetName": "example",
            "sourceRepo": "splice",
            "sourceFilepath": "values.yaml",
            "location": {"type": "fullFile"},
            "options": {"language": "yaml"},
        },
        {old: new},
    )
    pin = SourcePin(
        "splice",
        "canton-network/splice",
        "a9076eb91f87a9bd9315d2f9e122d6350bdc9d4c",
    )

    rendered = declaration(item, pin, f"See {old}")

    assert f'replaceFrom="{old}"' in rendered
    assert 'replaceWith="[current docs](/current)"' in rendered
    assert 'trim="true"' not in rendered


def test_page_migration_preserves_frontmatter_and_other_imports(
    tmp_path: Path, monkeypatch
) -> None:
    docs = tmp_path / "docs-main"
    page = docs / "page.mdx"
    docs.mkdir()
    page.write_text(
        """---
title: Pilot
---
import Other from "/other.mdx";
import Example from "/snippets/external/splice/main/example.mdx";

<Other />
<Example />
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(migrate_legacy, "DOCS_ROOT", docs)

    used, pages = migrate_legacy.migrate_pages(
        {("splice", "example"): '<Snippet source="ref" language="yaml" />'}
    )

    source = docs / "page.source.mdx"
    rendered = source.read_text(encoding="utf-8")
    assert rendered.startswith("---\ntitle: Pilot\n---")
    assert 'import Other from "/other.mdx";' in rendered
    assert "import Example" not in rendered
    assert '<Snippet source="ref" language="yaml" />' in rendered
    assert used == {("splice", "example")}
    assert pages == {source}
