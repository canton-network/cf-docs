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


def test_declares_manifest_requested_full_file_trimming() -> None:
    item = snippet(
        {
            "snippetName": "debug-values",
            "sourceRepo": "cn-quickstart",
            "sourceFilepath": "debug.yaml",
            "location": {"type": "fullFile"},
            "options": {"language": "yaml", "trim": True},
        }
    )
    pin = SourcePin(
        "cn-quickstart",
        "digital-asset/cn-quickstart",
        "41f2d75cd16eff28aedfaf2e9a2278a881b1c71a",
    )

    rendered = declaration(item, pin, "services: {}")

    assert 'trim="true"' in rendered


def test_declares_trailing_whitespace_cleanup_only_when_legacy_output_needs_it() -> (
    None
):
    item = snippet(
        {
            "snippetName": "example",
            "sourceRepo": "daml-shell",
            "sourceFilepath": "docs/example.rst",
            "location": {"type": "lines", "start": 1, "end": 2},
            "options": {"language": "shell"},
        }
    )
    pin = SourcePin(
        "daml-shell",
        "DACH-NY/daml-shell",
        "b4e42bef9f2fe1dbbb88633d733b06f79cd9ccd3",
    )

    rendered = declaration(item, pin, "source", "line with space \n")

    assert 'stripTrailingWhitespace="true"' in rendered


def test_legacy_audit_ignores_only_the_wrapper_terminal_newline() -> None:
    assert migrate_legacy._without_terminal_newline("body\n") == "body"
    assert migrate_legacy._without_terminal_newline("body") == "body"
    assert migrate_legacy._without_terminal_newline("body\n\n") == "body\n"


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


def test_page_migration_extends_an_existing_authoring_source(
    tmp_path: Path, monkeypatch
) -> None:
    docs = tmp_path / "docs-main"
    docs.mkdir()
    generated = docs / "page.mdx"
    generated.write_text(
        """---
title: Pilot
---
{/* Generated from page.source.mdx. Do not edit this file directly. */}
import Second from "/snippets/external/splice/main/second.mdx";

{/* source: first */}
```yaml
first
```
<Second />
""",
        encoding="utf-8",
    )
    source = docs / "page.source.mdx"
    source.write_text(
        """---
title: Pilot
---
import Second from "/snippets/external/splice/main/second.mdx";

<Snippet source="first" language="yaml" />
<Second />
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(migrate_legacy, "DOCS_ROOT", docs)

    used, pages = migrate_legacy.migrate_pages(
        {("splice", "second"): '<Snippet source="second" language="yaml" />'}
    )

    rewritten = source.read_text(encoding="utf-8")
    assert "Generated from" not in rewritten
    assert '<Snippet source="first" language="yaml" />' in rewritten
    assert '<Snippet source="second" language="yaml" />' in rewritten
    assert "import Second" not in rewritten
    assert used == {("splice", "second")}
    assert pages == {source}


def test_page_migration_includes_reusable_and_generated_partials(
    tmp_path: Path, monkeypatch
) -> None:
    docs = tmp_path / "docs-main"
    wrapper = docs / "snippets" / "external" / "splice" / "main" / "common.mdx"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text(
        """import Example from "/snippets/external/splice/main/example.mdx";

Before
<Example />
After
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(migrate_legacy, "DOCS_ROOT", docs)

    used, pages = migrate_legacy.migrate_pages(
        {("splice", "example"): '<Snippet source="ref" language="yaml" />'}
    )

    source = wrapper.with_name("common.source.mdx")
    assert source.is_file()
    assert '<Snippet source="ref" language="yaml" />' in source.read_text(
        encoding="utf-8"
    )
    assert used == {("splice", "example")}
    assert pages == {source}


def test_page_migration_is_transactional_when_a_reference_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    docs = tmp_path / "docs-main"
    docs.mkdir()
    page = docs / "page.mdx"
    original = """import Example from "/snippets/external/splice/main/example.mdx";

<Example />
"""
    page.write_text(original, encoding="utf-8")
    monkeypatch.setattr(migrate_legacy, "DOCS_ROOT", docs)

    try:
        migrate_legacy.migrate_pages(
            {
                ("splice", "example"): '<Snippet source="one" language="yaml" />',
                ("splice", "missing"): '<Snippet source="two" language="yaml" />',
            }
        )
    except migrate_legacy.LegacyMigrationError as error:
        assert "splice:missing" in str(error)
    else:
        raise AssertionError("missing reference should abort migration")

    assert page.read_text(encoding="utf-8") == original
    assert not (docs / "page.source.mdx").exists()
