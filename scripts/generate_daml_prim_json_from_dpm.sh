#!/usr/bin/env bash
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: generate_daml_prim_json_from_dpm.sh --output-json PATH [options]

Generate daml-prim docs JSON using dpm/damlc from installed SDK artifacts.

Options:
  --output-json PATH   Destination JSON file path. (required)
  --sdk-version VER    SDK version to use. Default: latest stable from get.digitalasset.com.
  --lf-target VER      LF target folder (e.g. 2.2). Default: highest numeric target available.
  --dpm-home PATH      DPM home dir. Default: $DPM_HOME or ~/.dpm
  --skip-install       Skip `dpm install`.
  -h, --help           Show this help.

Environment:
  DAML_DOCS_SDK_VERSION  Default for --sdk-version.
  DAML_DOCS_LF_TARGET    Default for --lf-target.
  DPM_HOME               Default for --dpm-home.

Example:
  ./scripts/generate_daml_prim_json_from_dpm.sh \
    --output-json /tmp/daml-prim.json \
    --sdk-version 3.4.10 \
    --lf-target 2.2
USAGE
}

log() {
  printf '[daml-prim-json] %s\n' "$*"
}

require_arg() {
  local flag="$1"
  local value="${2:-}"
  if [[ -z "$value" ]]; then
    echo "Missing value for $flag" >&2
    usage >&2
    exit 1
  fi
}

latest_sdk_version() {
  curl -fsSL "https://get.digitalasset.com/install/latest"
}

pick_default_lf_target() {
  local pkg_db_root="$1"
  python3 - "$pkg_db_root" <<'PY'
import os
import re
import sys

root = sys.argv[1]
entries = [
    d
    for d in os.listdir(root)
    if os.path.isdir(os.path.join(root, d))
]
numeric = [d for d in entries if re.fullmatch(r"\d+\.\d+", d)]
if numeric:
    numeric.sort(key=lambda s: tuple(int(p) for p in s.split(".")))
    print(numeric[-1])
    raise SystemExit(0)

if not entries:
    raise SystemExit(1)

entries.sort()
print(entries[-1])
PY
}

OUTPUT_JSON=""
SDK_VERSION="${DAML_DOCS_SDK_VERSION:-latest}"
LF_TARGET="${DAML_DOCS_LF_TARGET:-}"
DPM_HOME_DIR="${DPM_HOME:-$HOME/.dpm}"
SKIP_INSTALL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-json)
      OUTPUT_JSON="$2"
      shift 2
      ;;
    --sdk-version)
      SDK_VERSION="$2"
      shift 2
      ;;
    --lf-target)
      LF_TARGET="$2"
      shift 2
      ;;
    --dpm-home)
      DPM_HOME_DIR="$2"
      shift 2
      ;;
    --skip-install)
      SKIP_INSTALL=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_arg "--output-json" "$OUTPUT_JSON"
require_arg "--dpm-home" "$DPM_HOME_DIR"

if ! command -v dpm >/dev/null 2>&1; then
  echo "dpm not found in PATH." >&2
  exit 1
fi

if [[ "$SDK_VERSION" == "latest" ]]; then
  SDK_VERSION="$(latest_sdk_version)"
fi
require_arg "--sdk-version" "$SDK_VERSION"

if [[ "$SKIP_INSTALL" == false ]]; then
  log "Installing SDK ${SDK_VERSION} via dpm"
  dpm install "$SDK_VERSION"
fi

PKG_DB_ROOT="$DPM_HOME_DIR/cache/components/damlc/$SDK_VERSION/damlc-dist-dpm/resources/pkg-db_dir"
if [[ ! -d "$PKG_DB_ROOT" ]]; then
  echo "Package DB root not found: $PKG_DB_ROOT" >&2
  echo "Check sdk version and DPM_HOME. (sdk=$SDK_VERSION, dpm_home=$DPM_HOME_DIR)" >&2
  exit 1
fi

if [[ -z "$LF_TARGET" ]]; then
  LF_TARGET="$(pick_default_lf_target "$PKG_DB_ROOT")"
fi
require_arg "--lf-target" "$LF_TARGET"

SRC_ROOT="$PKG_DB_ROOT/$LF_TARGET/daml-prim"
if [[ ! -d "$SRC_ROOT" ]]; then
  echo "daml-prim source dir not found: $SRC_ROOT" >&2
  echo "Available LF targets under $PKG_DB_ROOT:" >&2
  find "$PKG_DB_ROOT" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort >&2 || true
  exit 1
fi

mapfile -t DAML_FILES < <(find "$SRC_ROOT" -type f -name '*.daml' | sort)
if [[ "${#DAML_FILES[@]}" -eq 0 ]]; then
  echo "No .daml files found under $SRC_ROOT" >&2
  exit 1
fi

mkdir -p "$(dirname -- "$OUTPUT_JSON")"

log "Generating daml-prim JSON"
log "sdk=$SDK_VERSION lf_target=$LF_TARGET files=${#DAML_FILES[@]}"
dpm damlc docs \
  --output "$OUTPUT_JSON" \
  --package-name daml-prim \
  --format json \
  -Wno-deprecated-exceptions \
  --target "$LF_TARGET" \
  "${DAML_FILES[@]}"

log "Wrote $OUTPUT_JSON"
