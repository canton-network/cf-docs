from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.harness.refresh_characterization_daml_json import refresh as refresh_daml_json
from tests.harness.refresh_characterization_jvm_docs import refresh as refresh_jvm_docs
from tests.harness.refresh_characterization_asyncapi import refresh as refresh_asyncapi
from tests.harness.refresh_characterization_openrpc import refresh as refresh_openrpc
from tests.harness.refresh_characterization_protobuf import refresh as refresh_protobuf
from tests.harness.refresh_characterization_typedoc import refresh as refresh_typedoc


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh rendered characterization fixtures for x2mdx.")
    parser.add_argument(
        "--format",
        action="append",
        choices=["jvm-docs", "daml-json", "protobuf", "typedoc", "asyncapi", "openrpc"],
        help="Format to refresh. Repeat to refresh multiple formats. Defaults to all.",
    )
    parser.add_argument("--force-download", action="store_true", help="Force jar re-downloads for JVM docs.")
    parser.add_argument("--force-regenerate", action="store_true", help="Force local regeneration for DAML JSON and TypeDoc.")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip git fetch before protobuf refresh.")
    parser.add_argument("--force-refresh", action="store_true", help="Force descriptor-image refresh for protobuf.")
    args = parser.parse_args()

    selected = set(args.format or ["jvm-docs", "daml-json", "protobuf", "typedoc", "asyncapi", "openrpc"])
    if "jvm-docs" in selected:
        refresh_jvm_docs(force_download=args.force_download)
    if "daml-json" in selected:
        refresh_daml_json(force_regenerate=args.force_regenerate)
    if "protobuf" in selected:
        refresh_protobuf(skip_fetch=args.skip_fetch, force_refresh=args.force_refresh)
    if "typedoc" in selected:
        refresh_typedoc(force_regenerate=args.force_regenerate)
    if "asyncapi" in selected:
        refresh_asyncapi(skip_fetch=args.skip_fetch)
    if "openrpc" in selected:
        refresh_openrpc(skip_fetch=args.skip_fetch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
