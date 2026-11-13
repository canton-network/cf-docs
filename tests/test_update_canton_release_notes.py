from __future__ import annotations

import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path
from types import ModuleType

import pytest


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


def write_source_config(path: Path, *, publish_version: str = "3.5") -> None:
    path.write_text(
        json.dumps(
            {
                "release_url_template": "https://www.canton.io/releases/canton-open-source-{canton_version}.tar.gz",
                "publish_version": publish_version,
                "versions": [{"version": publish_version, "canton_version": f"{publish_version}.1"}],
            }
        ),
        encoding="utf-8",
    )


def stub_github_releases(monkeypatch, module, releases: list[dict[str, object]]) -> list[str]:
    requested: list[str] = []

    def github_api_json(path: str) -> object:
        requested.append(path)
        return releases if path.endswith("&page=1") else []

    monkeypatch.setattr(module.canton_release_reference, "github_api_json", github_api_json)
    return requested


def test_release_note_sources_include_every_published_release_line(monkeypatch, tmp_path: Path) -> None:
    module = load_script_module()
    source_config = tmp_path / "source-artifacts.json"
    write_source_config(source_config)
    requested = stub_github_releases(
        monkeypatch,
        module,
        [
            {"tag_name": "v3.6.1", "draft": False, "prerelease": False},
            {"tag_name": "v3.5.10", "draft": False, "prerelease": False},
            {"tag_name": "v3.5.6", "draft": False, "prerelease": False},
            {"tag_name": "v3.4.12", "draft": False, "prerelease": False},
        ],
    )
    monkeypatch.setattr(module.canton_release_bundles, "release_bundle_exists", lambda _config, **_kwargs: True)

    sources = module.release_note_sources(
        source_config_path=source_config,
        release_repo="digital-asset/canton",
        min_version=module.Version.parse("3.5.0"),
        version_prefix=None,
    )

    assert requested[0] == "repos/digital-asset/canton/releases?per_page=100&page=1"
    assert [str(source.version) for source in sources] == ["3.5.6", "3.5.10", "3.6.1"]
    assert [source.archive_path for source in sources] == [
        "canton-open-source-3.5.6/RELEASE-NOTES.md",
        "canton-open-source-3.5.10/RELEASE-NOTES.md",
        "canton-open-source-3.6.1/RELEASE-NOTES.md",
    ]
    assert sources[-1].url == "https://www.canton.io/releases/canton-open-source-3.6.1.tar.gz"


def test_release_note_sources_skip_versions_without_a_published_release(monkeypatch, tmp_path: Path) -> None:
    module = load_script_module()
    source_config = tmp_path / "source-artifacts.json"
    write_source_config(source_config)
    stub_github_releases(
        monkeypatch,
        module,
        [
            {"tag_name": "v3.6.2", "draft": True, "prerelease": False},
            {"tag_name": "v3.6.1", "draft": False, "prerelease": False},
            {"tag_name": "v3.6.1-rc1", "draft": False, "prerelease": True},
            {"tag_name": "v3.5.11", "draft": False, "prerelease": False},
            {"tag_name": "v3.5.10", "draft": False, "prerelease": False},
        ],
    )
    checked: list[str] = []
    monkeypatch.setattr(
        module.canton_release_bundles,
        "release_bundle_exists",
        lambda _config, *, canton_version: checked.append(canton_version) or canton_version != "3.5.11",
    )

    sources = module.release_note_sources(
        source_config_path=source_config,
        release_repo="digital-asset/canton",
        min_version=module.Version.parse("3.5.0"),
        version_prefix=None,
    )

    # 3.6.0 has a public bundle but no GitHub release, so it is never considered.
    assert "3.6.0" not in checked
    assert [str(source.version) for source in sources] == ["3.5.10", "3.6.1"]


def test_release_note_sources_can_select_release_line(monkeypatch, tmp_path: Path) -> None:
    module = load_script_module()
    source_config = tmp_path / "source-artifacts.json"
    write_source_config(source_config)
    stub_github_releases(
        monkeypatch,
        module,
        [
            {"tag_name": "v3.6.1", "draft": False, "prerelease": False},
            {"tag_name": "v3.5.6", "draft": False, "prerelease": False},
        ],
    )
    monkeypatch.setattr(module.canton_release_bundles, "release_bundle_exists", lambda _config, **_kwargs: True)

    sources = module.release_note_sources(
        source_config_path=source_config,
        release_repo="digital-asset/canton",
        min_version=module.Version.parse("3.5.0"),
        version_prefix="3.5",
    )

    assert [str(source.version) for source in sources] == ["3.5.6"]


def test_fetch_release_note_markdown_reads_release_bundle(monkeypatch) -> None:
    module = load_script_module()
    markdown = b"# Release of Canton 3.5.13\n\nPublished notes.\n"
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode="w:gz") as archive:
        member = tarfile.TarInfo("canton-open-source-3.5.13/RELEASE-NOTES.md")
        member.size = len(markdown)
        archive.addfile(member, io.BytesIO(markdown))
    bundle_bytes = bundle.getvalue()
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: io.BytesIO(bundle_bytes))
    source = module.ReleaseNoteSource(
        module.Version.parse("3.5.13"),
        "https://www.canton.io/releases/canton-open-source-3.5.13.tar.gz",
        "canton-open-source-3.5.13/RELEASE-NOTES.md",
    )

    assert module.fetch_release_note_markdown(source=source) == markdown.decode("utf-8")


def test_release_section_demotes_headings_and_qualifies_ids() -> None:
    module = load_script_module()
    markdown = """# Release of Canton 3.5.6

## Summary

See [breaking changes](#breaking-changes) and [the second note](#note-2).

## Breaking changes

### Note

### Note

```
# not a heading
```
"""

    section = module.release_section(markdown, module.Version.parse("3.5.6"))
    resolved = module.resolve_release_links({module.Version.parse("3.5.6"): section})

    assert resolved[module.Version.parse("3.5.6")] == """## Release of Canton 3.5.6 {#release-of-canton-3-5-6}

### Summary {#summary-3-5-6}

See [breaking changes](#breaking-changes-3-5-6) and [the second note](#note-2-3-5-6).

### Breaking changes {#breaking-changes-3-5-6}

#### Note {#note-3-5-6}

#### Note {#note-2-3-5-6}

```
# not a heading
```"""


def test_release_section_anchors_deep_headings_with_an_element() -> None:
    module = load_script_module()
    version = module.Version.parse("3.5.6")
    markdown = "# Release of Canton 3.5.6\n\nSee [deep](#deep-heading).\n\n#### Deep heading\n\nText.\n"

    section = module.release_section(markdown, version)
    resolved = module.resolve_release_links({version: section})[version]

    assert '<a id="deep-heading-3-5-6" />\n##### Deep heading\n' in resolved
    assert "[deep](#deep-heading-3-5-6)" in resolved
    assert module.assign_heading_ids(resolved, version) == resolved


def test_resolve_release_links_rejects_unknown_anchors() -> None:
    module = load_script_module()
    version = module.Version.parse("3.5.6")
    section = module.release_section("# Release of Canton 3.5.6\n\nSee [missing](#missing).\n", version)

    with pytest.raises(ValueError, match="#missing"):
        module.resolve_release_links({version: section})


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


def run_update(module, tmp_path: Path, release_dir: Path, docs_json: Path):
    release_notes = release_dir.parent
    return module.update_release_pages(
        release_dir=release_dir,
        legacy_release_index=release_notes / "canton.mdx",
        legacy_release_page=release_notes / "canton" / "index.mdx",
        legacy_release_dir=release_notes / "canton",
        docs_json=docs_json,
        source_config_path=tmp_path / "source-artifacts.json",
        release_repo="digital-asset/canton",
        min_version=module.Version.parse("3.5.0"),
        version_prefix=None,
        dry_run=False,
    )


def source(module, version: str):
    return module.ReleaseNoteSource(
        module.Version.parse(version),
        f"https://www.canton.io/releases/canton-open-source-{version}.tar.gz",
        f"canton-open-source-{version}/RELEASE-NOTES.md",
    )


def test_update_release_pages_downloads_only_missing_releases(monkeypatch, tmp_path: Path) -> None:
    module = load_script_module()
    release_dir = tmp_path / "canton-releases"
    release_dir.mkdir()
    sources = (source(module, "3.5.11"), source(module, "3.5.12"), source(module, "3.5.13"))
    (release_dir / "3-5.mdx").write_text(
        '---\ntitle: "3.5"\n---\n\n## Release of Canton 3.5.12 {#release-of-canton-3-5-12}\n\nOn page.\n',
        encoding="utf-8",
    )
    (release_dir / "3-5-11.mdx").write_text(
        '---\ntitle: "3.5.11"\n---\n\n# Release of Canton 3.5.11\n\nLegacy page.\n', encoding="utf-8"
    )
    downloaded: list[tuple[object, ...]] = []
    monkeypatch.setattr(module, "release_note_sources", lambda **_kwargs: sources)
    monkeypatch.setattr(
        module,
        "read_source_markdown",
        lambda *, sources: downloaded.append(tuple(sources)) or {},
    )
    monkeypatch.setattr(module, "write_minor_pages", lambda **_kwargs: (True, ()))
    monkeypatch.setattr(module, "update_docs_json", lambda **_kwargs: False)

    update = run_update(module, tmp_path, release_dir, tmp_path / "docs.json")

    assert downloaded == [(sources[2],)]
    assert update.previous_versions == ("3.5.11", "3.5.12")


def test_resolve_release_links_points_cross_release_links_at_the_minor_page() -> None:
    module = load_script_module()
    older = module.Version.parse("3.5.1")
    newer = module.Version.parse("3.6.1")
    sections = {
        older: module.release_section("# Release of Canton 3.5.1\n\n## Targeting LF 2.3\n", older),
        newer: module.release_section(
            "# Release of Canton 3.6.1\n\n"
            "See [LF 2.3](https://docs.canton.network/global-synchronizer/release-notes/canton-releases/3-5-1#targeting-lf-2-3)"
            " and [3.5.1](/global-synchronizer/release-notes/canton-releases/3-5-1).\n",
            newer,
        ),
    }

    resolved = module.resolve_release_links(sections)

    assert (
        "[LF 2.3](https://docs.canton.network/global-synchronizer/release-notes/canton-releases/3-5#targeting-lf-2-3-3-5-1)"
        in resolved[newer]
    )
    assert "[3.5.1](/global-synchronizer/release-notes/canton-releases/3-5#release-of-canton-3-5-1)" in resolved[newer]
    assert module.resolve_release_links(resolved) == resolved


def test_update_release_pages_writes_minor_pages_nav_and_redirects(monkeypatch, tmp_path: Path) -> None:
    module = load_script_module()
    release_notes = tmp_path / "docs-main" / "global-synchronizer" / "release-notes"
    release_dir = release_notes / "canton-releases"
    docs_json = tmp_path / "docs-main" / "docs.json"
    release_dir.mkdir(parents=True)
    (release_notes / "canton.mdx").write_text(
        '---\ntitle: "Canton"\n---\n\n- [Canton 3.5.3](/global-synchronizer/release-notes/canton-releases/3-5-3)\n',
        encoding="utf-8",
    )
    (release_dir / "3-5-3.mdx").write_text(
        '---\ntitle: "3.5.3"\n---\n\n# Release of Canton 3.5.3\n\n## Summary\n\nReviewed 353.\n',
        encoding="utf-8",
    )
    canton_group = """{
                "group": "Canton",
                "pages": [
                  "global-synchronizer/release-notes/canton",
                  "global-synchronizer/release-notes/canton-releases/3-5-3"
                ]
              }"""
    docs_json.write_text(
        f"""{{
  "navigation": {{
    "products": [
      {{
        "product": "Global Synchronizer",
        "groups": [
          {{
            "group": "Release Notes",
            "pages": ["global-synchronizer/release-notes/splice", {canton_group}]
          }}
        ]
      }},
      {{
        "product": "Release Notes",
        "pages": [
          {{
            "group": "Canton Network",
            "pages": ["global-synchronizer/release-notes/splice", {canton_group}]
          }}
        ]
      }}
    ]
  }},
  "redirects": []
}}
""",
        encoding="utf-8",
    )
    sources = (source(module, "3.5.3"), source(module, "3.5.4"), source(module, "3.6.1"))
    monkeypatch.setattr(module, "release_note_sources", lambda **_kwargs: sources)
    monkeypatch.setattr(
        module,
        "read_source_markdown",
        lambda *, sources: {
            item: f"# Release of Canton {item.version}\n\n## Summary\n\nRelease {item.version}.\n" for item in sources
        },
    )

    update = run_update(module, tmp_path, release_dir, docs_json)

    assert update.previous_versions == ("3.5.3",)
    assert update.current_versions == ("3.5.3", "3.5.4", "3.6.1")
    assert update.changed is True
    assert not (release_notes / "canton.mdx").exists()
    assert sorted(path.name for path in release_dir.iterdir()) == ["3-5.mdx", "3-6.mdx"]
    assert (release_dir / "3-5.mdx").read_text(encoding="utf-8") == """---
title: "3.5"
description: "Canton 3.5 release notes."
---

{/* Generated from the RELEASE-NOTES.md files in public Canton release bundles. */}

## Release of Canton 3.5.4 {#release-of-canton-3-5-4}

### Summary {#summary-3-5-4}

Release 3.5.4.

## Release of Canton 3.5.3 {#release-of-canton-3-5-3}

### Summary {#summary-3-5-3}

Reviewed 353.
"""
    docs = json.loads(docs_json.read_text(encoding="utf-8"))
    expected_nav = [
        "global-synchronizer/release-notes/splice",
        {
            "group": "Canton",
            "pages": [
                "global-synchronizer/release-notes/canton-releases/3-6",
                "global-synchronizer/release-notes/canton-releases/3-5",
            ],
        },
    ]
    assert docs["navigation"]["products"][0]["groups"][0]["pages"] == expected_nav
    assert docs["navigation"]["products"][1]["pages"][0]["pages"] == expected_nav
    assert docs["redirects"] == [
        {
            "source": "/global-synchronizer/release-notes/canton",
            "destination": "/global-synchronizer/release-notes/canton-releases/3-6",
        },
        {
            "source": "/global-synchronizer/release-notes/canton-releases/3-5-3",
            "destination": "/global-synchronizer/release-notes/canton-releases/3-5#release-of-canton-3-5-3",
        },
    ]

    assert run_update(module, tmp_path, release_dir, docs_json).changed is False


def test_update_redirects_moves_the_canton_index_to_the_newest_line() -> None:
    module = load_script_module()
    docs = {
        "redirects": [
            {
                "source": "/global-synchronizer/release-notes/canton",
                "destination": "/global-synchronizer/release-notes/canton-releases/3-7",
            }
        ]
    }

    module.update_redirects(docs, removed_slugs=(), newest_line=(3, 8))

    assert docs["redirects"] == [
        {
            "source": "/global-synchronizer/release-notes/canton",
            "destination": "/global-synchronizer/release-notes/canton-releases/3-8",
        }
    ]
