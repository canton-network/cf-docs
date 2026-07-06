from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "update_release_notes.py"
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


def test_package_release_pages_record_upstream_source_metadata() -> None:
    module = load_script_module()
    target = module.PACKAGE_RELEASE_TARGETS["wallet-gateway"]
    releases = (
        module.PackageRelease(
            version=module.Version.parse("1.5.0"),
            tag_name="@canton-network/wallet-gateway-remote@1.5.0",
            published_at="2026-06-29T15:49:35Z",
            body="## 1.5.0 (2026-06-29)\n\n- changed <placeholder>",
            html_url="https://github.com/example/release",
        ),
    )
    sections = module.package_release_sections(releases)
    release_target = module.WALLET_RELEASE_TARGETS["wallet-gateway"]

    index_page = module.release_index_page(release_target, sections)
    release_page = module.release_page(release_target, sections[0])

    assert 'title: "Wallet Gateway"' in index_page
    assert 'latest_version="1.5.0"' in index_page
    assert "[Wallet Gateway 1.5.0 — 2026-06-29](/integrations/release-notes/wallet-gateway-releases/1-5-0)" in index_page
    assert 'title: "1.5.0 — 2026-06-29"' in release_page
    assert 'version="1.5.0"' in release_page
    assert "# 1.5.0 — 2026-06-29" in release_page
    assert "- changed &lt;placeholder&gt;" in release_page


def test_rst_to_mdx_converts_wallet_sdk_headings_links_and_code_blocks() -> None:
    module = load_script_module()
    rst = """Wallet SDK Release Notes
========================

1.3.1
-----

**Released on May 20th, 2026**

* plugin support with ``registerPlugins``

.. code-block:: javascript

    const sdk = await SDK.create()

* :doc:`Wallet SDK v1 Migration Guide <../wallet-sdk-v1-migration-guide/index>`
"""

    mdx = module.rst_to_mdx(rst, source_repo="canton-network/wallet", source_ref="abc123")

    assert "Wallet SDK Release Notes" not in mdx
    assert "## 1.3.1" in mdx
    assert "- plugin support with `registerPlugins`" in mdx
    assert "```javascript\nconst sdk = await SDK.create()\n```" in mdx
    assert (
        "[Wallet SDK v1 Migration Guide]"
        "(https://github.com/canton-network/wallet/blob/abc123/"
        "docs/wallet-integration-guide/src/wallet-sdk-v1-migration-guide/index.rst)"
    ) in mdx


def test_wallet_sdk_sections_use_source_sha_for_links_and_metadata() -> None:
    module = load_script_module()
    source = module.GithubContent(
        text="""Wallet SDK Release Notes
========================

1.3.1
-----

**Released on May 20th, 2026**
""",
        sha="65a1c2d",
        html_url="https://github.com/canton-network/wallet/blob/main/docs/index.rst",
    )

    intro, sections = module.wallet_sdk_sections(source)
    release_target = module.WALLET_RELEASE_TARGETS["wallet-sdk"]
    index_page = module.release_index_page(release_target, sections)
    release_page = module.release_page(release_target, sections[0])

    assert intro == ""
    assert 'latest_version="1.3.1"' in index_page
    assert 'latest_source="65a1c2d"' in index_page
    assert "[Wallet SDK 1.3.1](/integrations/release-notes/wallet-sdk-releases/1-3-1)" in index_page
    assert 'source="65a1c2d"' in release_page
    assert "# 1.3.1" in release_page


def test_splice_sections_from_source_converts_release_note_directives() -> None:
    module = load_script_module()
    source = module.GithubContent(
        text=""".. release-notes:: Upcoming

    * unreleased change

.. release-notes:: 0.6.6

    * Validator change with ``code``
    * :doc:`Validator docs <validator_operator/index>`

.. release-notes:: 0.6.5

    * Scan change
""",
        sha="bceda3b",
        html_url="https://github.com/canton-network/splice/blob/main/docs/src/release_notes.rst",
    )

    sections = module.splice_sections_from_source(source)

    assert [str(section.version) for section in sections] == ["0.6.6", "0.6.5"]
    assert sections[0].title == "0.6.6"
    assert sections[0].source_id == "bceda3b"
    assert "## 0.6.6" in sections[0].body
    assert "- Validator change with `code`" in sections[0].body
    assert (
        "[Validator docs]"
        "(https://github.com/canton-network/splice/blob/bceda3b/docs/src/validator_operator/index.rst)"
    ) in sections[0].body


def test_existing_splice_sections_merge_duplicate_version_headings() -> None:
    module = load_script_module()
    markdown = """---
title: "Splice"
description: "Release notes"
---

## 0.6.7 Release Notes amend

Amendment body.

## 0.6.7

Original body.

## 0.6.6

Older body.
"""

    _intro, sections = module.split_version_heading_sections(
        markdown,
        source_id="existing",
        source_url="docs-main/global-synchronizer/release-notes/splice.mdx",
    )

    assert [str(section.version) for section in sections] == ["0.6.7", "0.6.6"]
    assert sections[0].title == "0.6.7"
    assert "## 0.6.7 Release Notes amend" in sections[0].body
    assert "## 0.6.7\n\nOriginal body." in sections[0].body


def test_update_docs_json_nests_splice_release_pages_in_canton_network_groups(tmp_path: Path) -> None:
    module = load_script_module()
    docs_json = tmp_path / "docs.json"
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
              "global-synchronizer/release-notes/splice"
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
              "global-synchronizer/release-notes/splice"
            ]
          },
          {
            "group": "Wallet Integration",
            "pages": []
          }
        ]
      }
    ]
  }
}
""",
        encoding="utf-8",
    )
    sections = (
        module.ReleaseNoteSection(
            version=module.Version.parse("0.6.6"),
            title="0.6.6",
            body="## 0.6.6",
            source_id="sha",
            source_url="https://github.com/canton-network/splice",
        ),
    )

    changed = module.update_docs_json(
        target=module.SPLICE_RELEASE_TARGET,
        sections=sections,
        docs_json=docs_json,
    )
    docs = docs_json.read_text(encoding="utf-8")

    assert changed is True
    assert docs.count('"group": "Splice"') == 2
    assert '"global-synchronizer/release-notes/splice-releases/0-6-6"' in docs
