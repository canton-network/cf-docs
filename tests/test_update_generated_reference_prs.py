from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "update_generated_reference_prs.py"
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


def test_selected_surfaces_defaults_to_all_surfaces() -> None:
    module = load_script_module()

    assert module.selected_surfaces(None) == module.SURFACES


def test_selected_surfaces_preserves_declared_surface_order() -> None:
    module = load_script_module()

    surfaces = module.selected_surfaces(["wallet-gateway-openrpc", "version-dashboard"])

    assert [surface.key for surface in surfaces] == ["version-dashboard", "wallet-gateway-openrpc"]


def test_generated_clean_paths_include_surface_paths_and_internal_output() -> None:
    module = load_script_module()

    clean_paths = module.generated_clean_paths()

    assert ".internal" in clean_paths
    assert "docs-main/reference/wallet-gateway-json-rpc" in clean_paths
    assert "docs-main/snippets/generated/version-dashboard-data.mdx" in clean_paths


def test_body_markdown_includes_description_changes_and_validation() -> None:
    module = load_script_module()
    surface = next(surface for surface in module.SURFACES if surface.key == "wallet-gateway-openrpc")

    body = module.body_markdown(
        surface=surface,
        changes=["- Wallet Gateway OpenRPC publish_version: 0.25.0 -> 1.4.0"],
    )

    assert body.startswith("Updates the Wallet Gateway OpenRPC source pin")
    assert "Version changes:\n- Wallet Gateway OpenRPC publish_version: 0.25.0 -> 1.4.0" in body
    assert "- `npm run generate:wallet-gateway-openrpc-reference`" in body


def test_body_markdown_notes_when_no_versions_changed() -> None:
    module = load_script_module()
    surface = next(surface for surface in module.SURFACES if surface.key == "version-dashboard")

    body = module.body_markdown(surface=surface, changes=[])

    assert "Version changes:\n- No version values changed." in body
