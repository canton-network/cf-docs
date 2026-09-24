from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "check_generated_docs_dependencies.py"
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[script_path.stem] = module
    spec.loader.exec_module(module)
    return module


def test_validate_commands_requires_nix_store_paths(monkeypatch) -> None:
    module = load_script_module()
    paths = {
        "declared": "/nix/store/example/bin/declared",
        "host-only": "/usr/bin/host-only",
    }
    monkeypatch.setattr(module.shutil, "which", paths.get)

    assert module.validate_commands(("declared", "host-only", "missing")) == [
        "command is not supplied by the Nix environment: host-only -> /usr/bin/host-only",
        "missing command: missing",
    ]


def test_missing_python_modules_reports_unavailable_modules(monkeypatch) -> None:
    module = load_script_module()
    monkeypatch.setattr(
        module.importlib.util,
        "find_spec",
        lambda name: object() if name == "available" else None,
    )

    assert module.missing_python_modules(("available", "missing")) == ["missing"]
