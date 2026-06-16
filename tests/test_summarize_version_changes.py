from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "summarize_version_changes.py"
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[script_path.stem] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def dashboard_payload(*, splice_version: str, dar_version: str) -> dict:
    return {
        "repositories": {
            "splice": {
                "versionMapping": {
                    "mainnet": {"externalVersion": splice_version},
                    "testnet": {"externalVersion": splice_version},
                }
            },
            "walletGateway": {
                "versionMapping": {
                    "mainnet": {"externalVersion": "1.4.0"},
                }
            },
        },
        "versions": {
            "mainnet": {
                "advanced": {
                    "darVersions": [
                        {"name": "splice-wallet", "version": dar_version},
                    ]
                }
            }
        },
    }


def test_dashboard_changes_summarizes_component_and_dar_versions(tmp_path: Path) -> None:
    module = load_script_module()
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    write_json(before, dashboard_payload(splice_version="0.6.5", dar_version="0.1.18"))
    write_json(after, dashboard_payload(splice_version="0.6.7", dar_version="0.1.19"))

    assert module.dashboard_changes(before, after) == [
        "- MainNet Splice: 0.6.5 -> 0.6.7",
        "- TestNet Splice: 0.6.5 -> 0.6.7",
        "- MainNet splice-wallet DAR: 0.1.18 -> 0.1.19",
    ]


def test_dashboard_changes_reports_no_changes(tmp_path: Path) -> None:
    module = load_script_module()
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    payload = dashboard_payload(splice_version="0.6.5", dar_version="0.1.18")
    write_json(before, payload)
    write_json(after, payload)

    assert module.dashboard_changes(before, after) == []


def test_source_config_changes_summarizes_publish_version(tmp_path: Path) -> None:
    module = load_script_module()
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    write_json(before, {"publish_version": "0.25.0", "min_version": "0.24.0"})
    write_json(after, {"publish_version": "1.4.0", "min_version": "0.24.0"})

    assert module.source_config_changes(before, after, label="Wallet Gateway OpenRPC") == [
        "- Wallet Gateway OpenRPC publish_version: 0.25.0 -> 1.4.0"
    ]
