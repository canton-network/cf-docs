#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from generated_reference_sources import splice_openapi, wallet_gateway_openrpc
from generated_reference_sources.common import SourceUpdate


SOURCE_SPLICE_OPENAPI = splice_openapi.SOURCE_KEY
SOURCE_WALLET_GATEWAY_OPENRPC = wallet_gateway_openrpc.SOURCE_KEY
ALL_SOURCES = (SOURCE_SPLICE_OPENAPI, SOURCE_WALLET_GATEWAY_OPENRPC)


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
