from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TAG_PREFIX = "@canton-network/wallet-gateway-remote@"


def load_generator():
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    name = "generate_wallet_gateway_openrpc_reference"
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_stable_release_versions_pages_through_the_whole_release_list(monkeypatch) -> None:
    generator = load_generator()
    # The repository hosts many packages, so a package's older releases sit on later pages.
    page_one = [{"tag_name": f"@canton-network/core-types@{index}.0.0"} for index in range(98)]
    page_one += [
        {"tag_name": f"{TAG_PREFIX}1.15.0"},
        {"tag_name": f"{TAG_PREFIX}1.11.3-backport.0"},
    ]
    page_two = [
        {"tag_name": f"{TAG_PREFIX}1.4.0"},
        {"tag_name": f"{TAG_PREFIX}0.24.0"},
        {"tag_name": f"{TAG_PREFIX}0.23.0"},
    ]
    requested: list[str] = []

    def fake_gh(args: list[str], *, capture: bool = False) -> str:
        requested.append(args[1])
        page = int(args[1].rsplit("page=", 1)[1])
        return json.dumps([page_one, page_two][page - 1])

    monkeypatch.setattr(generator, "gh", fake_gh)

    versions = generator.stable_release_versions(
        release_repo="canton-network/wallet",
        tag_prefix=TAG_PREFIX,
        min_version="0.24.0",
        max_version=None,
        include_versions=None,
    )

    assert versions == ["0.24.0", "1.4.0", "1.15.0"]
    assert len(requested) == 2
