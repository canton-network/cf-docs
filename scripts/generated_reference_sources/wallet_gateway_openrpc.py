from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Required, TypedDict

import generate_wallet_gateway_openrpc_reference as wallet_gateway_openrpc_generator

from generated_reference_sources.common import SourceUpdate, load_json, write_json


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_KEY = "wallet-gateway-openrpc"
SOURCE_LABEL = "Wallet Gateway OpenRPC"
DEFAULT_SOURCE_CONFIG = (
    REPO_ROOT / "config" / "x2mdx" / "wallet-gateway-openrpc" / "source-artifacts.json"
)


class WalletGatewayOpenRpcSpecConfig(TypedDict, total=False):
    spec_id: str
    display_name: str
    source_path: str


class WalletGatewayOpenRpcSourceConfigPayload(TypedDict, total=False):
    source: str
    release_repo: Required[str]
    remote: str
    tag_prefix: Required[str]
    min_version: str
    publish_version: Required[str]
    specs: list[WalletGatewayOpenRpcSpecConfig]


@dataclass(frozen=True)
class WalletGatewayOpenRpcSourceConfig:
    raw: WalletGatewayOpenRpcSourceConfigPayload
    release_repo: str
    tag_prefix: str
    min_version: str
    publish_version: str


def parse_source_config(path: Path) -> WalletGatewayOpenRpcSourceConfig:
    raw_json = load_json(path)
    release_repo = raw_json.get("release_repo")
    tag_prefix = raw_json.get("tag_prefix")
    min_version = raw_json.get("min_version") or "0.0.0"
    publish_version = raw_json.get("publish_version")
    if not isinstance(release_repo, str) or not release_repo:
        raise ValueError("Wallet Gateway OpenRPC source config must define release_repo")
    if not isinstance(tag_prefix, str) or not tag_prefix:
        raise ValueError("Wallet Gateway OpenRPC source config must define tag_prefix")
    if not isinstance(min_version, str):
        raise ValueError("Wallet Gateway OpenRPC min_version must be a string")
    if not isinstance(publish_version, str) or not publish_version:
        raise ValueError(f"{path} must define non-empty publish_version")
    raw: WalletGatewayOpenRpcSourceConfigPayload = {}
    raw.update(raw_json)
    return WalletGatewayOpenRpcSourceConfig(
        raw=raw,
        release_repo=release_repo,
        tag_prefix=tag_prefix,
        min_version=min_version,
        publish_version=publish_version,
    )


def latest_version(source_config: WalletGatewayOpenRpcSourceConfig) -> str:
    versions = wallet_gateway_openrpc_generator.stable_release_versions(
        release_repo=source_config.release_repo,
        tag_prefix=source_config.tag_prefix,
        min_version=source_config.min_version,
        max_version=None,
        include_versions=None,
    )
    if not versions:
        raise ValueError("No Wallet Gateway OpenRPC releases selected")
    return versions[-1]


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> SourceUpdate | None:
    source_config = parse_source_config(source_config_path)
    current_version = latest_version(source_config)
    if source_config.publish_version == current_version:
        return None

    update = SourceUpdate(
        source=SOURCE_LABEL,
        path=source_config_path,
        field="publish_version",
        previous=source_config.publish_version,
        current=current_version,
    )
    if not dry_run:
        updated_config = dict(source_config.raw)
        updated_config["publish_version"] = current_version
        write_json(source_config_path, updated_config)
    return update
