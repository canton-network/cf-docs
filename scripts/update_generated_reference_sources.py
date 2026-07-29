#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from generated_reference_sources import (
    canton_release_bundles,
    daml_script,
    daml_standard_library,
    ledger_bindings,
    splice_openapi,
    typescript_bindings,
    wallet_gateway_openrpc,
)
from generated_reference_sources.common import SourceUpdate


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DAML_SCRIPT = daml_script.SOURCE_KEY
SOURCE_DAML_STANDARD_LIBRARY = daml_standard_library.SOURCE_KEY
SOURCE_LEDGER_API = "ledger-api"
SOURCE_LEDGER_API_ASYNCAPI = "ledger-api-asyncapi"
SOURCE_LEDGER_BINDINGS = ledger_bindings.SOURCE_KEY
SOURCE_SPLICE_OPENAPI = splice_openapi.SOURCE_KEY
SOURCE_WALLET_GATEWAY_OPENRPC = wallet_gateway_openrpc.SOURCE_KEY
SOURCE_TYPESCRIPT_BINDINGS = typescript_bindings.SOURCE_KEY
DEFAULT_LEDGER_API_SOURCE_CONFIG = REPO_ROOT / "config" / "x2mdx" / "ledger-api" / "source-artifacts.json"
DEFAULT_LEDGER_API_ASYNCAPI_SOURCE_CONFIG = (
    REPO_ROOT / "config" / "x2mdx" / "ledger-api-asyncapi" / "source-artifacts.json"
)
ALL_SOURCES = (
    SOURCE_SPLICE_OPENAPI,
    SOURCE_WALLET_GATEWAY_OPENRPC,
    SOURCE_TYPESCRIPT_BINDINGS,
    SOURCE_LEDGER_API,
    SOURCE_LEDGER_API_ASYNCAPI,
    SOURCE_LEDGER_BINDINGS,
    SOURCE_DAML_STANDARD_LIBRARY,
    SOURCE_DAML_SCRIPT,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update committed generated-reference source pins to their latest source versions."
    )
    parser.add_argument(
        "--splice-openapi-source-config",
        type=Path,
        default=splice_openapi.DEFAULT_SOURCE_CONFIG,
        help=f"Splice OpenAPI source-artifacts config. Default: {splice_openapi.DEFAULT_SOURCE_CONFIG}",
    )
    parser.add_argument(
        "--wallet-gateway-openrpc-source-config",
        type=Path,
        default=wallet_gateway_openrpc.DEFAULT_SOURCE_CONFIG,
        help=(
            "Wallet Gateway OpenRPC source-artifacts config. "
            f"Default: {wallet_gateway_openrpc.DEFAULT_SOURCE_CONFIG}"
        ),
    )
    parser.add_argument(
        "--typescript-bindings-source-config",
        type=Path,
        default=typescript_bindings.DEFAULT_SOURCE_CONFIG,
        help=(
            "TypeScript bindings source-artifacts config. "
            f"Default: {typescript_bindings.DEFAULT_SOURCE_CONFIG}"
        ),
    )
    parser.add_argument(
        "--ledger-api-source-config",
        type=Path,
        default=DEFAULT_LEDGER_API_SOURCE_CONFIG,
        help=f"JSON Ledger API OpenAPI source-artifacts config. Default: {DEFAULT_LEDGER_API_SOURCE_CONFIG}",
    )
    parser.add_argument(
        "--ledger-api-asyncapi-source-config",
        type=Path,
        default=DEFAULT_LEDGER_API_ASYNCAPI_SOURCE_CONFIG,
        help=(
            "JSON Ledger API AsyncAPI source-artifacts config. "
            f"Default: {DEFAULT_LEDGER_API_ASYNCAPI_SOURCE_CONFIG}"
        ),
    )
    parser.add_argument(
        "--ledger-bindings-source-config",
        type=Path,
        default=ledger_bindings.DEFAULT_SOURCE_CONFIG,
        help=f"Ledger bindings source-artifacts config. Default: {ledger_bindings.DEFAULT_SOURCE_CONFIG}",
    )
    parser.add_argument(
        "--daml-standard-library-source-config",
        type=Path,
        default=daml_standard_library.DEFAULT_SOURCE_CONFIG,
        help=(
            "Daml Standard Library source-artifacts config. "
            f"Default: {daml_standard_library.DEFAULT_SOURCE_CONFIG}"
        ),
    )
    parser.add_argument(
        "--daml-script-source-config",
        type=Path,
        default=daml_script.DEFAULT_SOURCE_CONFIG,
        help=f"Daml Script source-artifacts config. Default: {daml_script.DEFAULT_SOURCE_CONFIG}",
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=ALL_SOURCES,
        dest="sources",
        help=(
            "Limit updates to one source. Repeat to update multiple sources. "
            "By default, all generated-reference sources are checked."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report updates without writing source config files.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with status 1 if any source pins are stale.",
    )
    return parser.parse_args()


def requested_sources(args: argparse.Namespace) -> tuple[str, ...]:
    return tuple(dict.fromkeys(args.sources or ALL_SOURCES))


def main() -> int:
    args = parse_args()
    sources = requested_sources(args)
    updates: list[SourceUpdate] = []
    if SOURCE_SPLICE_OPENAPI in sources:
        update = splice_openapi.update_source(
            source_config_path=args.splice_openapi_source_config.resolve(),
            dry_run=args.dry_run or args.check,
        )
        if update is not None:
            updates.append(update)
    if SOURCE_WALLET_GATEWAY_OPENRPC in sources:
        update = wallet_gateway_openrpc.update_source(
            source_config_path=args.wallet_gateway_openrpc_source_config.resolve(),
            dry_run=args.dry_run or args.check,
        )
        if update is not None:
            updates.append(update)
    if SOURCE_TYPESCRIPT_BINDINGS in sources:
        updates.extend(
            typescript_bindings.update_source(
                source_config_path=args.typescript_bindings_source_config.resolve(),
                dry_run=args.dry_run or args.check,
            )
        )
    if SOURCE_LEDGER_API in sources:
        update = canton_release_bundles.update_source(
            source_config_path=args.ledger_api_source_config.resolve(),
            dry_run=args.dry_run or args.check,
        )
        if update is not None:
            updates.append(update)
    if SOURCE_LEDGER_API_ASYNCAPI in sources:
        update = canton_release_bundles.update_source(
            source_config_path=args.ledger_api_asyncapi_source_config.resolve(),
            dry_run=args.dry_run or args.check,
        )
        if update is not None:
            updates.append(update)
    if SOURCE_LEDGER_BINDINGS in sources:
        updates.extend(
            ledger_bindings.update_source(
                source_config_path=args.ledger_bindings_source_config.resolve(),
                dry_run=args.dry_run or args.check,
            )
        )
    if SOURCE_DAML_STANDARD_LIBRARY in sources:
        update = daml_standard_library.update_source(
            source_config_path=args.daml_standard_library_source_config.resolve(),
            dry_run=args.dry_run or args.check,
        )
        if update is not None:
            updates.append(update)
    if SOURCE_DAML_SCRIPT in sources:
        update = daml_script.update_source(
            source_config_path=args.daml_script_source_config.resolve(),
            dry_run=args.dry_run or args.check,
        )
        if update is not None:
            updates.append(update)

    if not updates:
        print("Generated reference source pins are up to date.")
        return 0

    for update in updates:
        action = "Would update" if args.dry_run or args.check else "Updated"
        print(
            f"{action} {update.source} {update.field}: "
            f"{update.previous} -> {update.current} ({update.path})"
        )
    if args.check:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
