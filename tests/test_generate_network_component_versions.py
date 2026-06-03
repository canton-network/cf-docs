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
    os.environ.setdefault("DIGITAL_ASSET_DOCS_DIRENV", "1")
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_preserves_generated_at_when_only_timestamp_changes() -> None:
    module = load_script("generate_network_component_versions")
    existing = {
        "_generated": {
            "generatedAt": "2026-06-01T00:00:00+00:00",
            "generatorMode": "public_source_collection_with_manual_fallbacks",
        },
        "versions": {"mainnet": {"name": "MainNet"}},
        "repositories": {"splice": {"url": "https://example.com"}},
    }
    candidate = {
        "_generated": {
            "generatedAt": "2026-06-03T12:00:00+00:00",
            "generatorMode": "public_source_collection_with_manual_fallbacks",
        },
        "versions": {"mainnet": {"name": "MainNet"}},
        "repositories": {"splice": {"url": "https://example.com"}},
    }

    result = module.preserve_generated_at_if_only_timestamp_changed(existing, candidate)

    assert result["_generated"]["generatedAt"] == "2026-06-01T00:00:00+00:00"


def test_keeps_new_generated_at_when_dashboard_data_changes() -> None:
    module = load_script("generate_network_component_versions")
    existing = {
        "_generated": {"generatedAt": "2026-06-01T00:00:00+00:00"},
        "versions": {"mainnet": {"substitutions": {"version": "0.6.2"}}},
        "repositories": {},
    }
    candidate = {
        "_generated": {"generatedAt": "2026-06-03T12:00:00+00:00"},
        "versions": {"mainnet": {"substitutions": {"version": "0.6.3"}}},
        "repositories": {},
    }

    result = module.preserve_generated_at_if_only_timestamp_changed(existing, candidate)

    assert result["_generated"]["generatedAt"] == "2026-06-03T12:00:00+00:00"
