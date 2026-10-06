from __future__ import annotations

import importlib.util
import io
import json
import sys
import tarfile
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


def test_update_release_page_downloads_only_missing_release_pages(monkeypatch, tmp_path: Path) -> None:
    module = load_script_module()
    release_dir = tmp_path / "canton-releases"
    release_dir.mkdir()
    sources = (
        module.ReleaseNoteSource(
            module.Version.parse("3.5.12"),
            "https://example.com/3.5.12.tar.gz",
            "3.5.12/RELEASE-NOTES.md",
        ),
        module.ReleaseNoteSource(
            module.Version.parse("3.5.13"),
            "https://example.com/3.5.13.tar.gz",
            "3.5.13/RELEASE-NOTES.md",
        ),
    )
    module.release_page_path(release_dir, sources[0]).write_text("existing\n", encoding="utf-8")
    downloaded: list[tuple[module.ReleaseNoteSource, ...]] = []
    monkeypatch.setattr(module, "release_note_sources", lambda **_kwargs: sources)
    monkeypatch.setattr(
        module,
        "read_source_markdown",
        lambda *, sources: downloaded.append(tuple(sources)) or {},
    )
    monkeypatch.setattr(module, "write_release_pages", lambda **_kwargs: True)
    monkeypatch.setattr(module, "update_docs_json", lambda **_kwargs: False)

    module.update_release_page(
        release_index=tmp_path / "canton.mdx",
        release_dir=release_dir,
        legacy_release_page=tmp_path / "legacy" / "index.mdx",
        legacy_release_dir=tmp_path / "legacy",
        docs_json=tmp_path / "docs.json",
        source_config_path=tmp_path / "source-artifacts.json",
        release_repo="digital-asset/canton",
        min_version=module.Version.parse("3.5.0"),
        version_prefix=None,
        dry_run=False,
    )

    assert downloaded == [(sources[1],)]


def test_release_index_markdown_links_each_release_newest_first() -> None:
    module = load_script_module()
    sources = (
        module.ReleaseNoteSource(
            module.Version.parse("3.5.4"),
            "https://www.canton.io/releases/canton-open-source-3.5.4.tar.gz",
            "canton-open-source-3.5.4/RELEASE-NOTES.md",
        ),
        module.ReleaseNoteSource(
            module.Version.parse("3.5.6"),
            "https://www.canton.io/releases/canton-open-source-3.5.6.tar.gz",
            "canton-open-source-3.5.6/RELEASE-NOTES.md",
        ),
    )

    assert module.release_index_markdown(sources) == """---
title: "Canton"
description: "Release notes for Canton."
---

{/* Generated from the RELEASE-NOTES.md files in public Canton release bundles. */}

Canton release notes are reproduced below from the published Canton release bundles.

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
        module.ReleaseNoteSource(
            module.Version.parse("3.5.3"),
            "https://www.canton.io/releases/canton-open-source-3.5.3.tar.gz",
            "canton-open-source-3.5.3/RELEASE-NOTES.md",
        ),
        module.ReleaseNoteSource(
            module.Version.parse("3.5.4"),
            "https://www.canton.io/releases/canton-open-source-3.5.4.tar.gz",
            "canton-open-source-3.5.4/RELEASE-NOTES.md",
        ),
        module.ReleaseNoteSource(
            module.Version.parse("3.5.6"),
            "https://www.canton.io/releases/canton-open-source-3.5.6.tar.gz",
            "canton-open-source-3.5.6/RELEASE-NOTES.md",
        ),
    )
    monkeypatch.setattr(module, "release_note_sources", lambda **_kwargs: sources)
    monkeypatch.setattr(
        module,
        "read_source_markdown",
        lambda **_kwargs: {
            sources[0]: "# Release of Canton 3.5.3\n\nRelease 353.\n",
            sources[1]: "# Release of Canton 3.5.4\n\nRelease 354.\n",
            sources[2]: "# Release of Canton 3.5.6\n\nRelease 356.\n",
        },
    )

    update = module.update_release_page(
        release_index=release_index,
        release_dir=release_dir,
        legacy_release_page=legacy_release_page,
        legacy_release_dir=legacy_release_dir,
        docs_json=docs_json,
        source_config_path=tmp_path / "source-artifacts.json",
        release_repo="digital-asset/canton",
        min_version=module.Version.parse("3.5.0"),
        version_prefix=None,
        dry_run=False,
    )

    assert update.previous_versions == ("3.5.3",)
    assert update.current_versions == ("3.5.3", "3.5.4", "3.5.6")
    assert update.changed is True
    assert not legacy_release_page.exists()
    assert not (legacy_release_dir / "3-5-3.mdx").exists()
    assert (release_dir / "3-5-3.mdx").exists()
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
