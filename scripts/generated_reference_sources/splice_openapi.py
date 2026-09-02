from __future__ import annotations

from pathlib import Path

from generated_reference_sources.common import SourceUpdate, load_json


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_KEY = "splice-openapi"
DEFAULT_SOURCE_CONFIG = (
    REPO_ROOT / "config" / "mintlify-openapi" / "splice-openapi" / "source-artifacts.json"
)


def update_source(
    *,
    source_config_path: Path,
    dry_run: bool,
) -> SourceUpdate | None:
    # Splice is intentionally unpinned: the generator resolves every eligible stable
    # release and publishes the latest selection on each run. Keep this compatibility
    # entry point as a no-op for callers that still include every source updater.
    _ = dry_run
    load_json(source_config_path)
    return None
