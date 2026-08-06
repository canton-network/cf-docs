from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    previous = os.environ.get("DIGITAL_ASSET_DOCS_DIRENV")
    os.environ["DIGITAL_ASSET_DOCS_DIRENV"] = "1"
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            os.environ.pop("DIGITAL_ASSET_DOCS_DIRENV", None)
        else:
            os.environ["DIGITAL_ASSET_DOCS_DIRENV"] = previous
    return module


def test_checked_in_docs_do_not_wrap_reference_cards_in_links() -> None:
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "docs-main").rglob("*.mdx")
        if '<a class="x2mdx-ref-card"' in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_asyncapi_card_normalization_supports_title_only_links() -> None:
    generator = load_script("generate_json_api_asyncapi_reference")
    rendered = """<div class="x2mdx-ref-card-grid">
  <div class="x2mdx-ref-card">
    <div class="x2mdx-ref-card-head">
      <a class="x2mdx-ref-card-title" href="./subscribe">Subscribe stream</a>
      <div class="x2mdx-ref-badges"><span>stable</span></div>
    </div>
    <p class="x2mdx-ref-card-summary">Original summary.</p>
    <dl class="x2mdx-ref-meta-grid">
      <div class="x2mdx-ref-meta-item">
        <dt>Method</dt>
        <dd>subscribe</dd>
      </div>
    </dl>
  </div>
</div>
"""

    normalized = generator.normalize_card_markup(
        rendered,
        summaries_by_href={"./subscribe": "Receive updates from /stream."},
    )

    assert '<a class="x2mdx-ref-card-title" href="./subscribe">' in normalized
    assert '<a class="x2mdx-ref-card"' not in normalized
    assert "Original summary." not in normalized
    assert "Receive updates from /stream." in normalized
    assert "x2mdx-ref-meta-item" in normalized
    assert normalized.index("Receive updates from /stream.") < normalized.index("x2mdx-ref-badges")
