from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "update_canton_release_notes.py"
    scripts_dir = str(script_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[script_path.stem] = module
    spec.loader.exec_module(module)
    return module


def test_selected_release_note_sources_default_to_latest_release_line(monkeypatch) -> None:
    module = load_script_module()

    monkeypatch.setattr(
        module,
        "github_request_json",
        lambda _url: [
            {"name": "3.5.6.md", "path": "release-notes/3.5.6.md", "sha": "sha-356"},
            {"name": "3.5.10.md", "path": "release-notes/3.5.10.md", "sha": "sha-3510"},
            {"name": "3.6.1.md", "path": "release-notes/3.6.1.md", "sha": "sha-361"},
            {"name": "README.md", "path": "release-notes/README.md", "sha": "sha-readme"},
        ],
    )

    sources = module.selected_release_note_sources(
        source_repo="digital-asset/canton",
        source_ref="main",
        version_prefix=None,
    )

    assert [str(source.version) for source in sources] == ["3.6.1"]
    assert [source.path for source in sources] == ["release-notes/3.6.1.md"]


def test_selected_release_note_sources_can_filter_release_line(monkeypatch) -> None:
    module = load_script_module()

    monkeypatch.setattr(
        module,
        "github_request_json",
        lambda _url: [
            {"name": "3.5.6.md", "path": "release-notes/3.5.6.md", "sha": "sha-356"},
            {"name": "3.6.1.md", "path": "release-notes/3.6.1.md", "sha": "sha-361"},
        ],
    )

    sources = module.selected_release_note_sources(
        source_repo="digital-asset/canton",
        source_ref="main",
        version_prefix="3.5",
    )

    assert [str(source.version) for source in sources] == ["3.5.6"]


def test_release_index_markdown_links_each_release_newest_first() -> None:
    module = load_script_module()
    sources = (
        module.ReleaseNoteSource(module.Version.parse("3.5.4"), "release-notes/3.5.4.md", "sha-354"),
        module.ReleaseNoteSource(module.Version.parse("3.5.6"), "release-notes/3.5.6.md", "sha-356"),
    )

    assert module.release_index_markdown(sources) == """---
title: "Canton"
description: "Release notes for Canton tools, including PQS, Daml Shell, Daml language, and more."
---

{/* Generated from upstream digital-asset/canton release-note sources. */}

Canton release notes are reproduced below from the upstream `digital-asset/canton` release-note sources.

## Releases

- [Canton 3.5.6](/global-synchronizer/release-notes/canton-releases/3-5-6)
- [Canton 3.5.4](/global-synchronizer/release-notes/canton-releases/3-5-4)
"""


def test_normalized_release_markdown_escapes_mdx_angle_placeholders_outside_code() -> None:
    module = load_script_module()
    markdown = """# Release of Canton 3.5.6

Text with <filter>, 3.25.5 --> 3.25.9, and `<node>.config`.

```
canton.participants.<participant>.config
```
"""

    assert module.normalized_release_markdown(markdown) == """# Release of Canton 3.5.6

Text with &lt;filter&gt;, 3.25.5 --&gt; 3.25.9, and `<node>.config`.

```
canton.participants.<participant>.config
```"""


def test_update_release_page_writes_index_pages_and_nav(monkeypatch, tmp_path: Path) -> None:
    module = load_script_module()
    release_index = tmp_path / "docs-main" / "global-synchronizer" / "release-notes" / "canton.mdx"
    release_dir = tmp_path / "docs-main" / "global-synchronizer" / "release-notes" / "canton-releases"
    legacy_release_dir = tmp_path / "docs-main" / "global-synchronizer" / "release-notes" / "canton"
    legacy_release_page = legacy_release_dir / "index.mdx"
    docs_json = tmp_path / "docs-main" / "docs.json"
    release_index.parent.mkdir(parents=True)
    release_index.write_text(
        """---
title: "Canton"
---

# Release of Canton 3.5.3

Old.
""",
        encoding="utf-8",
    )
    legacy_release_dir.mkdir(parents=True)
    legacy_release_page.write_text("stale index\n", encoding="utf-8")
    (legacy_release_dir / "3-5-3.mdx").write_text("stale release\n", encoding="utf-8")
    docs_json.write_text(
        """{
  "navigation": {
    "products": [
      {
        "product": "Global Synchronizer",
        "groups": [
          {
            "group": "Release Notes",
            "pages": [
              "global-synchronizer/release-notes/splice",
              "global-synchronizer/release-notes/canton",
              "global-synchronizer/release-notes/canton/3-5-3"
            ]
          }
        ]
      },
      {
        "product": "Release Notes",
        "pages": [
          {
            "group": "Canton Network",
            "pages": [
              "global-synchronizer/release-notes/splice",
              "global-synchronizer/release-notes/canton",
              "global-synchronizer/release-notes/canton/3-5-3"
            ]
          }
        ]
      }
    ]
  }
}
""",
        encoding="utf-8",
    )
    sources = (
        module.ReleaseNoteSource(module.Version.parse("3.5.4"), "release-notes/3.5.4.md", "sha-354"),
        module.ReleaseNoteSource(module.Version.parse("3.5.6"), "release-notes/3.5.6.md", "sha-356"),
    )
    monkeypatch.setattr(module, "selected_release_note_sources", lambda **_kwargs: sources)
    monkeypatch.setattr(
        module,
        "read_source_markdown",
        lambda **_kwargs: {
            sources[0]: "# Release of Canton 3.5.4\n\nRelease 354.\n",
            sources[1]: "# Release of Canton 3.5.6\n\nRelease 356.\n",
        },
    )

    update = module.update_release_page(
        release_index=release_index,
        release_dir=release_dir,
        legacy_release_page=legacy_release_page,
        legacy_release_dir=legacy_release_dir,
        docs_json=docs_json,
        source_repo="digital-asset/canton",
        source_ref="main",
        version_prefix=None,
        dry_run=False,
    )

    assert update.previous_versions == ("3.5.3",)
    assert update.current_versions == ("3.5.4", "3.5.6")
    assert update.changed is True
    assert not legacy_release_page.exists()
    assert not (legacy_release_dir / "3-5-3.mdx").exists()
    assert "/global-synchronizer/release-notes/canton-releases/3-5-6" in release_index.read_text(encoding="utf-8")
    assert (release_dir / "3-5-4.mdx").read_text(encoding="utf-8").startswith(
        '---\ntitle: "3.5.4"\ndescription: "Canton 3.5.4 release notes."\n---\n\n# Release of Canton 3.5.4'
    )
    assert "# Release of Canton 3.5.6\n\nRelease 356.\n" in (release_dir / "3-5-6.mdx").read_text(
        encoding="utf-8"
    )
    docs = docs_json.read_text(encoding="utf-8")
    assert '"group": "Canton"' in docs
    assert '"global-synchronizer/release-notes/canton"' in docs
    assert '"global-synchronizer/release-notes/canton-releases/3-5-6"' in docs
    assert '"global-synchronizer/release-notes/canton/3-5-3"' not in docs
