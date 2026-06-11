from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "update_generated_reference_sources.py"
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


def write_source_config(path: Path, *, publish_version: str) -> None:
    path.write_text(
        json.dumps(
            {
                "source": "test",
                "release_repo": "digital-asset/decentralized-canton-sync",
                "tag_regex": "^v(?P<version>0\\.[0-9]+\\.[0-9]+)$",
                "min_version": "0.5.10",
                "publish_version": publish_version,
                "asset_template": "{version}_openapi.tar.gz",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_update_splice_openapi_source_updates_stale_publish_version(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_source_config(source_config_path, publish_version="0.5.18")
    module.splice_openapi.selected_releases = lambda **_kwargs: [
        {"version": "0.5.18"},
        {"version": "0.6.7"},
    ]

    update = module.update_splice_openapi_source(
        source_config_path=source_config_path,
        dry_run=False,
    )

    assert update == module.SourceUpdate(
        source="Splice OpenAPI",
        path=source_config_path,
        field="publish_version",
        previous="0.5.18",
        current="0.6.7",
    )
    assert json.loads(source_config_path.read_text(encoding="utf-8"))["publish_version"] == "0.6.7"


def test_update_splice_openapi_source_noops_when_current(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_source_config(source_config_path, publish_version="0.6.7")
    module.splice_openapi.selected_releases = lambda **_kwargs: [
        {"version": "0.5.18"},
        {"version": "0.6.7"},
    ]

    assert (
        module.update_splice_openapi_source(
            source_config_path=source_config_path,
            dry_run=False,
        )
        is None
    )
    assert json.loads(source_config_path.read_text(encoding="utf-8"))["publish_version"] == "0.6.7"


def test_update_splice_openapi_source_dry_run_does_not_write(tmp_path: Path) -> None:
    module = load_script_module()
    source_config_path = tmp_path / "source-artifacts.json"
    write_source_config(source_config_path, publish_version="0.5.18")
    module.splice_openapi.selected_releases = lambda **_kwargs: [
        {"version": "0.5.18"},
        {"version": "0.6.7"},
    ]

    update = module.update_splice_openapi_source(
        source_config_path=source_config_path,
        dry_run=True,
    )

    assert update is not None
    assert update.previous == "0.5.18"
    assert update.current == "0.6.7"
    assert json.loads(source_config_path.read_text(encoding="utf-8"))["publish_version"] == "0.5.18"
