from __future__ import annotations

from pathlib import Path

from generated_reference_sources.common import SourceUpdate, load_json


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_KEY = "wallet-gateway-openrpc"
DEFAULT_SOURCE_CONFIG = (
    REPO_ROOT / "config" / "x2mdx" / "wallet-gateway-openrpc" / "source-artifacts.json"
)


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> SourceUpdate | None:
    # Wallet OpenRPC is intentionally unpinned: normal generation resolves every
    # eligible stable release and publishes the latest selection. Keep this entry
    # point as a compatibility no-op for the aggregate source updater.
    _ = dry_run
    load_json(source_config_path)
    return None
