#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import urllib.error
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_canton_topology_proto_link.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "generate_canton_topology_proto_link",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_canton_version_accepts_tag_and_bare_semver() -> None:
    module = load_module()

    assert module.parse_canton_version("v3.5.14") == "3.5.14"
    assert module.parse_canton_version("3.6.0") == "3.6.0"


def test_parse_canton_version_rejects_prerelease_and_garbage() -> None:
    module = load_module()

    with pytest.raises(ValueError):
        module.parse_canton_version("v3.5.14-snapshot.1")
    with pytest.raises(ValueError):
        module.parse_canton_version("release-line-3.5")


def test_release_line_branch_tracks_major_minor_for_future_lines() -> None:
    module = load_module()

    assert module.release_line_branch("3.5.14") == "release-line-3.5"
    assert module.release_line_branch("3.6.2") == "release-line-3.6"


def test_topology_proto_urls_use_release_line_and_fixed_path() -> None:
    module = load_module()

    assert module.topology_proto_blob_url("release-line-3.6") == (
        "https://github.com/digital-asset/canton/blob/release-line-3.6/"
        "community/base/src/main/protobuf/com/digitalasset/canton/protocol/v30/topology.proto"
    )
    assert module.topology_proto_raw_url("release-line-3.6") == (
        "https://raw.githubusercontent.com/digital-asset/canton/release-line-3.6/"
        "community/base/src/main/protobuf/com/digitalasset/canton/protocol/v30/topology.proto"
    )


def test_render_mdx_exports_only_topology_proto_url() -> None:
    module = load_module()
    url = (
        "https://github.com/digital-asset/canton/blob/release-line-3.5/"
        "community/base/src/main/protobuf/com/digitalasset/canton/protocol/v30/topology.proto"
    )

    rendered = module.render_mdx(url)

    assert rendered == f"export const topologyProtoUrl = '{url}';\n"
    assert "cantonVersion" not in rendered
    assert "releaseLineBranch" not in rendered


def test_assert_url_exists_raises_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()

    def boom(_request, timeout=None):  # noqa: ANN001
        raise urllib.error.HTTPError(
            url="https://example.test/missing",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", boom)

    with pytest.raises(RuntimeError, match="returned 404"):
        module.assert_url_exists("https://example.test/missing", timeout=1.0)


def test_write_output_for_derived_release_line(tmp_path: Path) -> None:
    module = load_module()
    output = tmp_path / "canton-topology-proto-link.mdx"
    canton_version = module.parse_canton_version("v3.6.1")
    release_line = module.release_line_branch(canton_version)
    blob_url = module.topology_proto_blob_url(release_line)

    module.write_output(output, module.render_mdx(blob_url))

    assert output.read_text(encoding="utf-8") == (
        "export const topologyProtoUrl = "
        "'https://github.com/digital-asset/canton/blob/release-line-3.6/"
        "community/base/src/main/protobuf/com/digitalasset/canton/protocol/v30/topology.proto';\n"
    )


def test_main_fails_when_url_check_returns_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    output = tmp_path / "canton-topology-proto-link.mdx"

    monkeypatch.setattr(module, "OUTPUT_PATH", output)
    monkeypatch.setattr(module, "fetch_latest_stable_canton_version", lambda _timeout: "9.9.0")

    def boom(_request, timeout=None):  # noqa: ANN001
        raise urllib.error.HTTPError(
            url="https://raw.githubusercontent.com/digital-asset/canton/release-line-9.9/missing",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", boom)

    assert module.main() == 1
    assert not output.exists()
