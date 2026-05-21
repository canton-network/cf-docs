from __future__ import annotations

import importlib.util
import json
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


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    write_json(
        repo / "config" / "x2mdx" / "daml-standard-library" / "source-artifacts.json",
        {"publish_version": "1.0.1", "versions": ["1.0.0", "1.0.1"]},
    )
    write_json(
        repo / "config" / "x2mdx" / "ledger-api" / "source-artifacts.json",
        {
            "release_url_template": "https://downloads.example/canton-{canton_version}.tar.gz",
            "publish_version": "1.0",
            "versions": [{"version": "1.0", "canton_version": "1.0.1"}],
        },
    )
    write_json(
        repo / "config" / "x2mdx" / "ledger-api-asyncapi" / "source-artifacts.json",
        {
            "release_url_template": "https://downloads.example/canton-{canton_version}.tar.gz",
            "publish_version": "1.0",
            "versions": [{"version": "1.0", "canton_version": "1.0.1"}],
        },
    )
    write_json(
        repo / "config" / "x2mdx" / "ledger-bindings" / "source-artifacts.json",
        {
            "repo_base": "https://repo.example/maven2",
            "artifacts": [
                {
                    "group": "com.daml",
                    "artifact": "bindings-java",
                    "language": "java",
                    "versions": ["1.0.0", "1.0.1"],
                }
            ],
        },
    )
    write_json(
        repo / "config" / "x2mdx" / "protobuf-history" / "source-artifacts.json",
        {
            "release_url_template": "https://downloads.example/canton-{version}.tar.gz",
            "min_version": "1.0.0",
            "excluded_versions": ["1.0.1"],
        },
    )
    write_json(
        repo / "config" / "x2mdx" / "grpc-ledger-api-reference" / "source-artifacts.json",
        {
            "release_url_template": "https://downloads.example/canton-{version}.tar.gz",
            "min_version": "1.1.0",
        },
    )
    write_json(
        repo / "config" / "x2mdx" / "typescript-bindings" / "source-artifacts.json",
        {
            "packages": [
                {
                    "package_name": "@daml/types",
                    "publish_version": "1.0.1",
                    "versions": ["1.0.0", "1.0.1"],
                },
                {
                    "package_name": "@canton-network/wallet-sdk",
                    "publish_version": "2.0.0",
                    "versions": ["2.0.0"],
                },
            ]
        },
    )
    write_json(
        repo / "config" / "x2mdx" / "wallet-gateway-openrpc" / "source-artifacts.json",
        {
            "release_repo": "owner/wallet",
            "tag_prefix": "@pkg@",
            "min_version": "0.1.0",
            "publish_version": "0.1.0",
        },
    )
    write_json(
        repo / "config" / "mintlify-openapi" / "splice-openapi" / "source-artifacts.json",
        {
            "release_repo": "owner/splice",
            "tag_regex": "^v(?P<version>\\d+\\.\\d+\\.\\d+)$",
            "asset_template": "{version}_openapi.tar.gz",
            "min_version": "1.0.0",
            "publish_version": "1.0.0",
        },
    )
    write_json(
        repo / "config" / "x2mdx" / "reference-update-policy.json",
        {
            "surfaces": {
                "daml": {
                    "kind": "git-tag-versions",
                    "config_path": "config/x2mdx/daml-standard-library/source-artifacts.json",
                    "repository": "owner/daml",
                    "tag_regex": "^v(?P<version>\\d+\\.\\d+\\.\\d+)$",
                    "keep": 2,
                    "publish_latest": True,
                },
                "json-ledger": {
                    "kind": "canton-release-bundle-minors",
                    "config_paths": [
                        "config/x2mdx/ledger-api/source-artifacts.json",
                        "config/x2mdx/ledger-api-asyncapi/source-artifacts.json",
                    ],
                    "repository": "owner/canton",
                    "tag_regex": "^v(?P<canton_version>\\d+\\.\\d+\\.\\d+)$",
                    "keep_minor_count": 2,
                    "validate_release_url": True,
                },
                "bindings": {
                    "kind": "maven-javadoc-artifact",
                    "config_path": "config/x2mdx/ledger-bindings/source-artifacts.json",
                    "keep": 2,
                    "validate_javadoc": True,
                },
                "protobuf": {
                    "kind": "canton-tag-versions",
                    "config_path": "config/x2mdx/protobuf-history/source-artifacts.json",
                    "repository": "owner/canton",
                    "tag_regex": "^v(?P<version>\\d+\\.\\d+\\.\\d+)$",
                    "validate_release_url": True,
                },
                "grpc": {
                    "kind": "canton-tag-versions",
                    "config_path": "config/x2mdx/grpc-ledger-api-reference/source-artifacts.json",
                    "repository": "owner/canton",
                    "tag_regex": "^v(?P<version>\\d+\\.\\d+\\.\\d+)$",
                    "validate_release_url": True,
                },
                "typescript": {
                    "kind": "npm-packages",
                    "config_path": "config/x2mdx/typescript-bindings/source-artifacts.json",
                    "keep": 2,
                    "publish_latest": True,
                },
                "wallet": {
                    "kind": "github-release-versions",
                    "config_path": "config/x2mdx/wallet-gateway-openrpc/source-artifacts.json",
                    "repository": "owner/wallet",
                    "tag_regex": "^@pkg@(?P<version>\\d+\\.\\d+\\.\\d+)$",
                    "keep": 2,
                    "publish_latest": True,
                },
                "splice": {
                    "kind": "github-release-asset-versions",
                    "config_path": "config/mintlify-openapi/splice-openapi/source-artifacts.json",
                    "repository": "owner/splice",
                    "tag_regex": "^v(?P<version>\\d+\\.\\d+\\.\\d+)$",
                    "asset_template": "{version}_openapi.tar.gz",
                    "keep": 1,
                    "publish_latest": True,
                },
            }
        },
    )
    return repo


def install_fake_discovery(module, monkeypatch) -> None:
    def fake_releases(path: str):
        if path == "repos/owner/daml/releases":
            return [{"tag_name": "v1.0.0"}, {"tag_name": "v1.0.1"}, {"tag_name": "v1.0.2"}]
        if path == "repos/owner/daml/tags":
            return [{"name": "v1.0.0"}, {"name": "v1.0.1"}, {"name": "v1.0.2"}]
        if path == "repos/owner/wallet/releases":
            return [{"tag_name": "@pkg@0.1.0"}, {"tag_name": "@pkg@0.2.0"}, {"tag_name": "@pkg@0.3.0"}]
        if path == "repos/owner/splice/releases":
            return [
                {
                    "tag_name": "v1.0.0",
                    "assets": [{"name": "1.0.0_openapi.tar.gz"}],
                },
                {
                    "tag_name": "v1.1.0",
                    "assets": [{"name": "1.1.0_openapi.tar.gz"}],
                },
            ]
        if path == "repos/owner/canton/tags":
            return [
                {"name": "v1.0.0"},
                {"name": "v1.0.1"},
                {"name": "v1.0.2"},
                {"name": "v1.1.0"},
                {"name": "v1.1.1"},
            ]
        raise AssertionError(path)

    def fake_text(url: str) -> str:
        assert url == "https://repo.example/maven2/com/daml/bindings-java/maven-metadata.xml"
        return """
<metadata>
  <versioning>
    <versions>
      <version>1.0.0</version>
      <version>1.0.1</version>
      <version>1.0.2</version>
    </versions>
  </versioning>
</metadata>
"""

    def fake_json(url: str):
        if url == "https://registry.npmjs.org/%40daml%2Ftypes":
            return {"versions": {"1.0.0": {}, "1.0.1": {}, "1.0.2": {}}}
        if url == "https://registry.npmjs.org/%40canton-network%2Fwallet-sdk":
            return {"versions": {"2.0.0": {}, "2.0.1": {}, "2.0.2": {}}}
        raise AssertionError(url)

    monkeypatch.setattr(module, "github_paginated", fake_releases)
    monkeypatch.setattr(module, "fetch_text_url", fake_text)
    monkeypatch.setattr(module, "fetch_json_url", fake_json)
    monkeypatch.setattr(module, "head_url", lambda url: True)


def test_apply_updates_source_configs_from_discovered_versions(tmp_path: Path, monkeypatch) -> None:
    module = load_script("update_reference_doc_sources")
    repo = prepare_repo(tmp_path)
    install_fake_discovery(module, monkeypatch)
    summary_path = repo / ".internal" / "summary.json"

    result = module.run(
        [
            "--apply",
            "--repo-root",
            str(repo),
            "--policy",
            str(repo / "config" / "x2mdx" / "reference-update-policy.json"),
            "--summary",
            str(summary_path),
        ]
    )

    assert result == 0
    summary = read_json(summary_path)
    assert summary["has_updates"] is True
    assert summary["updated_surfaces"] == [
        "daml",
        "json-ledger",
        "bindings",
        "protobuf",
        "grpc",
        "typescript",
        "wallet",
        "splice",
    ]
    assert read_json(repo / "config" / "x2mdx" / "daml-standard-library" / "source-artifacts.json") == {
        "publish_version": "1.0.2",
        "versions": ["1.0.1", "1.0.2"],
    }
    assert read_json(repo / "config" / "x2mdx" / "ledger-api" / "source-artifacts.json")["versions"] == [
        {"version": "1.0", "canton_version": "1.0.2"},
        {"version": "1.1", "canton_version": "1.1.1"},
    ]
    assert read_json(repo / "config" / "x2mdx" / "protobuf-history" / "source-artifacts.json")["versions"] == [
        "1.0.0",
        "1.0.2",
        "1.1.0",
        "1.1.1",
    ]
    assert read_json(repo / "config" / "x2mdx" / "grpc-ledger-api-reference" / "source-artifacts.json")["versions"] == [
        "1.1.0",
        "1.1.1",
    ]
    typescript = read_json(repo / "config" / "x2mdx" / "typescript-bindings" / "source-artifacts.json")
    assert typescript["packages"][0]["versions"] == ["1.0.1", "1.0.2"]
    assert typescript["packages"][1]["publish_version"] == "2.0.2"


def test_check_mode_reports_no_updates_without_rewriting(tmp_path: Path, monkeypatch) -> None:
    module = load_script("update_reference_doc_sources")
    repo = prepare_repo(tmp_path)
    install_fake_discovery(module, monkeypatch)
    policy = repo / "config" / "x2mdx" / "reference-update-policy.json"
    summary_path = repo / ".internal" / "summary.json"
    module.run(["--apply", "--repo-root", str(repo), "--policy", str(policy), "--summary", str(summary_path)])
    before = (repo / "config" / "x2mdx" / "typescript-bindings" / "source-artifacts.json").read_text(
        encoding="utf-8"
    )

    result = module.run(["--check", "--repo-root", str(repo), "--policy", str(policy), "--summary", str(summary_path)])

    assert result == 0
    assert read_json(summary_path)["has_updates"] is False
    after = (repo / "config" / "x2mdx" / "typescript-bindings" / "source-artifacts.json").read_text(
        encoding="utf-8"
    )
    assert after == before


def test_generators_use_configured_versions_as_default_pin() -> None:
    assert load_script("generate_canton_protobuf_history").configured_versions({"versions": ["1.2.3"]}) == {"1.2.3"}
    assert load_script("generate_grpc_ledger_api_reference").configured_versions({"versions": ["1.2.3"]}) == {"1.2.3"}
    assert load_script("generate_wallet_gateway_openrpc_reference").configured_versions({"versions": ["1.2.3"]}) == {
        "1.2.3"
    }
    assert load_script("generate_splice_mintlify_openapi").configured_versions({"versions": ["1.2.3"]}) == {"1.2.3"}
