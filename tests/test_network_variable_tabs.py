from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "generate_network_variable_tabs.py"
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


def sample_network_data() -> dict[str, object]:
    return {
        "devnet": {
            "name": "DevNet",
            "versions": {"splice": "0.6.4"},
            "substitutions": {
                "gsf_scan_url": "https://scan.dev.example",
                "bundle_download_link": {
                    "label": "Download Bundle",
                    "href": "https://download.dev.example/bundle.tgz",
                },
            },
        },
        "testnet": {
            "name": "TestNet",
            "versions": {"splice": "0.6.3"},
            "substitutions": {
                "gsf_scan_url": "https://scan.test.example",
                "bundle_download_link": {
                    "label": "Download Bundle",
                    "href": "https://download.test.example/bundle.tgz",
                },
            },
        },
    }


def test_load_network_data_preserves_export_in_substitution_strings(tmp_path: Path) -> None:
    module = load_script_module()
    network_data = tmp_path / "version-dashboard-data.mdx"
    network_data.write_text(
        """export const lastUpdatedAt = '2026-07-28T08:35:56+00:00';
export const lastUpdatedLabel = 'July 28, 2026';

export const networkData = {
  mainnet: {
    name: 'MainNet',
    versions: { splice: '0.6.12' },
    substitutions: {
      image_tag_set: 'export IMAGE_TAG=0.6.12',
      chart_version_set: 'export CHART_VERSION=0.6.12',
    },
  },
};
""",
        encoding="utf-8",
    )

    loaded = module.load_network_data(network_data)

    assert loaded["mainnet"]["substitutions"]["image_tag_set"] == "export IMAGE_TAG=0.6.12"
    assert loaded["mainnet"]["substitutions"]["chart_version_set"] == "export CHART_VERSION=0.6.12"


def write_template(docs_main: Path, relative: str, text: str) -> Path:
    path = docs_main / "src" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_render_network_tabs_inlines_imported_snippets_and_substitutes_tokens(tmp_path: Path) -> None:
    module = load_script_module()
    docs_main = tmp_path / "docs-main"
    imported = docs_main / "snippets" / "external" / "sample.mdx"
    imported.parent.mkdir(parents=True)
    imported.write_text(
        """```bash
curl |gsf_scan_url|/api/scan/v0/dso-sequencers
```
""",
        encoding="utf-8",
    )
    source = """import ExternalSample from "/snippets/external/sample.mdx";

Download from |bundle_download_link|.

<div data-network-only="devnet">
DevNet only: |gsf_scan_url|
</div>

- Nested command:

  <ExternalSample />

> <ExternalSample />

<ExternalSample />
"""
    imports, body = module.split_source_imports(source, docs_main)

    generated = module.render_network_tabs(body, imports, sample_network_data(), docs_main)

    assert generated.startswith("<Tabs>")
    assert generated.endswith("</Tabs>")
    assert '<Tab title="DevNet (0.6.4)">' in generated
    assert '<Tab title="TestNet (0.6.3)">' in generated
    assert "https://scan.dev.example/api/scan/v0/dso-sequencers" in generated
    assert "https://scan.test.example/api/scan/v0/dso-sequencers" in generated
    assert "  ```bash\n  curl https://scan.dev.example/api/scan/v0/dso-sequencers\n  ```" in generated
    assert "> ```bash\n> curl https://scan.dev.example/api/scan/v0/dso-sequencers\n> ```" in generated
    assert "\n  \n" not in generated
    assert "\n> \n" not in generated
    assert '<a href="https://download.dev.example/bundle.tgz">Download Bundle (DevNet 0.6.4)</a>' in generated
    testnet_tab = generated.split('<Tab title="TestNet (0.6.3)">', 1)[1]
    assert "DevNet only" not in testnet_tab
    assert "|gsf_scan_url|" not in generated


def test_template_renders_whole_page_and_is_idempotent(tmp_path: Path) -> None:
    module = load_script_module()
    docs_main = tmp_path / "docs-main"
    block_snippet = docs_main / "snippets" / "external" / "block.mdx"
    block_snippet.parent.mkdir(parents=True)
    block_snippet.write_text("Block snippet for |gsf_scan_url|\n", encoding="utf-8")
    (docs_main / "snippets" / "existing.mdx").write_text("Existing\n", encoding="utf-8")
    source = write_template(
        docs_main,
        "guide/example.mdx",
        """---
title: Example
hidden: true
---

import Existing from "/snippets/existing.mdx";

import BlockSnippet from "/snippets/external/block.mdx";

Editor prose before.

<Existing />

<Tabs>
  <Tab title="All networks">
    Scan URL: |gsf_scan_url|

    ```bash
    curl |gsf_scan_url|/api
    ```

    <BlockSnippet />
  </Tab>
</Tabs>

<Tabs>
<Tab title="Ordinary tab">
Kept as written: |gsf_scan_url|
</Tab>
</Tabs>

Editor prose after.
""",
    )
    output = docs_main / "guide" / "example.mdx"

    assert module.update_page(source, sample_network_data(), docs_main, check=True)
    assert not output.exists()
    assert module.update_page(source, sample_network_data(), docs_main)
    rendered = output.read_text(encoding="utf-8")
    assert rendered.startswith(
        "---\ntitle: Example\n---\n"
        "{/* Generated from /src/guide/example.mdx by `npm run generate:network-variable-tabs`. "
        "Edit that file, not this one. */}\n\n"
        'import Existing from "/snippets/existing.mdx";\n\nEditor prose before.'
    )
    assert "hidden: true" not in rendered
    assert 'title="All networks"' not in rendered
    assert "```bash\ncurl https://scan.dev.example/api\n```" in rendered
    assert '<Tab title="Ordinary tab">\nKept as written: |gsf_scan_url|\n</Tab>' in rendered
    assert "BlockSnippet" not in rendered
    assert "Scan URL: https://scan.dev.example" in rendered
    assert "Block snippet for https://scan.test.example" in rendered
    assert rendered.endswith("</Tabs>\n\nEditor prose after.\n")
    assert not module.update_page(source, sample_network_data(), docs_main)
    assert output.read_text(encoding="utf-8") == rendered


def test_template_must_be_hidden(tmp_path: Path) -> None:
    module = load_script_module()
    docs_main = tmp_path / "docs-main"
    source = write_template(docs_main, "visible.mdx", "---\ntitle: Visible\n---\n\nBody\n")

    with pytest.raises(ValueError, match="hidden: true"):
        module.render_page(source, sample_network_data(), docs_main)


def test_generated_page_without_template_is_orphaned(tmp_path: Path) -> None:
    module = load_script_module()
    docs_main = tmp_path / "docs-main"
    write_template(docs_main, "kept.mdx", "---\ntitle: Kept\nhidden: true\n---\n\nBody\n")
    for name in ("kept", "orphan"):
        (docs_main / f"{name}.mdx").write_text(
            f"---\ntitle: {name}\n---\n{module.generated_notice(f'/src/{name}.mdx')}\n\nBody\n",
            encoding="utf-8",
        )

    assert module.orphaned_outputs(docs_main) == [docs_main / "orphan.mdx"]


def test_validate_script_detects_hand_edited_output_without_writing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    docs_main = repo / "docs-main"
    network_data = docs_main / "snippets" / "generated" / "version-dashboard-data.mdx"
    network_data.parent.mkdir(parents=True)
    network_data.write_text(
        """export const networkData = {
  devnet: {
    name: "DevNet",
    versions: { splice: "0.6.4" },
    substitutions: { gsf_scan_url: "https://scan.dev.example" },
  },
};
""",
        encoding="utf-8",
    )
    write_template(
        docs_main,
        "example.mdx",
        "---\ntitle: Example\nhidden: true\n---\n\n<Tabs>\n<Tab title=\"All networks\">\nScan URL: |gsf_scan_url|\n</Tab>\n</Tabs>\n",
    )
    script_dir = repo / "scripts"
    script_dir.mkdir()
    generator = REPO_ROOT / "scripts" / "generate_network_variable_tabs.py"
    validator = REPO_ROOT / "scripts" / "validate_network_variable_tabs.py"
    (script_dir / generator.name).write_text(generator.read_text(encoding="utf-8"), encoding="utf-8")
    (script_dir / validator.name).write_text(validator.read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(
        [sys.executable, "scripts/generate_network_variable_tabs.py"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    page = docs_main / "example.mdx"
    assert "Scan URL: https://scan.dev.example" in page.read_text(encoding="utf-8")

    current = subprocess.run(
        [sys.executable, "scripts/validate_network_variable_tabs.py"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    assert current.returncode == 0
    assert "Network variable tabs are rendered and up to date." in current.stdout

    page.write_text(page.read_text() + "\nHand edit to the generated page.\n", encoding="utf-8")
    before = page.read_bytes()
    stale = subprocess.run(
        [sys.executable, "scripts/validate_network_variable_tabs.py"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    assert stale.returncode == 1
    assert "Network variable tabs are stale" in stale.stderr
    assert "docs-main/src/" in stale.stderr
    assert "docs-main/example.mdx" in stale.stderr
    assert page.read_bytes() == before


def test_generation_preserves_ordinary_editor_files(tmp_path: Path) -> None:
    module = load_script_module()
    docs_main = tmp_path / "docs-main"
    docs_main.mkdir()
    page = docs_main / "new-page.mdx"
    page.write_text('---\ntitle: New page\n---\n\n\nEditor content.\n', encoding="utf-8")
    navigation = docs_main / "docs.json"
    navigation.write_text('{"navigation":{"pages":["new-page"]}}\n', encoding="utf-8")
    image = docs_main / "new-image.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\neditor-upload")
    before = {path: path.read_bytes() for path in docs_main.iterdir()}

    assert module.iter_sources(docs_main) == []
    assert module.orphaned_outputs(docs_main) == []
    assert {path: path.read_bytes() for path in docs_main.iterdir()} == before


def test_checked_in_templates_are_hidden_listed_and_rendered() -> None:
    module = load_script_module()
    docs_main = REPO_ROOT / "docs-main"
    templates = module.iter_sources(docs_main)
    assert templates
    assert not (docs_main / "snippets" / "networkvars").exists()

    docs_json = json.loads((docs_main / "docs.json").read_text(encoding="utf-8"))
    template_product = next(
        product for product in docs_json["navigation"]["products"] if product["product"] == "Page templates"
    )
    assert template_product["hidden"] is True
    assert sorted(template_product["pages"]) == sorted(
        path.relative_to(docs_main).with_suffix("").as_posix() for path in templates
    )

    for template in templates:
        page = module.output_path_for_source(template, docs_main)
        text = page.read_text(encoding="utf-8")
        assert module.generated_notice(module.source_ref_for_path(template, docs_main)) in text
        assert '<Tab title="All networks">' not in text
        assert "<Tabs>" in text
        assert "<Tab title=" in text

    onboarding = docs_main / "global-synchronizer" / "deployment" / "onboarding-process.mdx"
    onboarding_text = onboarding.read_text(encoding="utf-8")
    assert "scan.sv-1.dev.global.canton.network.sync.global" in onboarding_text
    assert "dso-sequencers" in onboarding_text
