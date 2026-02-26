#!/usr/bin/env bash
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: generate_daml_prim_json_from_dpm.sh --output-json PATH [options]

Generate Daml docs JSON using dpm/damlc from installed SDK artifacts.

Options:
  --output-json PATH   Destination JSON file path. (required)
  --sdk-version VER    SDK version to use. Default: latest stable from get.digitalasset.com.
  --lf-target VER      LF target folder (e.g. 2.2). Default: highest numeric target available.
  --package-set SET    One of: prim, stdlib, base. Default: prim.
                       - prim:   only daml-prim modules
                       - stdlib: only daml-stdlib modules
                       - base:   stdlib + prim merged (matches docs pipeline composition)
  --dpm-home PATH      DPM home dir. Default: $DPM_HOME or ~/.dpm
  --skip-install       Skip `dpm install`.
  -h, --help           Show this help.

Environment:
  DAML_DOCS_SDK_VERSION  Default for --sdk-version.
  DAML_DOCS_LF_TARGET    Default for --lf-target.
  DAML_DOCS_PACKAGE_SET  Default for --package-set.
  DPM_HOME               Default for --dpm-home.

Example:
  ./scripts/generate_daml_prim_json_from_dpm.sh \
    --output-json /tmp/daml-prim.json \
    --sdk-version 3.4.10 \
    --lf-target 2.2 \
    --package-set base
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

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

OUTPUT_JSON=""
SDK_VERSION="${DAML_DOCS_SDK_VERSION:-latest}"
LF_TARGET="${DAML_DOCS_LF_TARGET:-}"
PACKAGE_SET="${DAML_DOCS_PACKAGE_SET:-prim}"
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
    --package-set)
      PACKAGE_SET="$2"
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
require_arg "--package-set" "$PACKAGE_SET"
if [[ "$PACKAGE_SET" != "prim" && "$PACKAGE_SET" != "stdlib" && "$PACKAGE_SET" != "base" ]]; then
  echo "Invalid --package-set '$PACKAGE_SET'. Expected one of: prim, stdlib, base." >&2
  exit 1
fi

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
  LF_TARGET="$(python3 "$SCRIPT_DIR/select_latest_lf_target.py" "$PKG_DB_ROOT")"
fi
require_arg "--lf-target" "$LF_TARGET"

TARGET_ROOT="$PKG_DB_ROOT/$LF_TARGET"
if [[ ! -d "$TARGET_ROOT" ]]; then
  echo "LF target root not found: $TARGET_ROOT" >&2
  echo "Available LF targets under $PKG_DB_ROOT:" >&2
  find "$PKG_DB_ROOT" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort >&2 || true
  exit 1
fi

resolve_stdlib_src_root() {
  local candidate
  candidate="$TARGET_ROOT/daml-stdlib-$SDK_VERSION"
  if [[ -d "$candidate" ]]; then
    echo "$candidate"
    return 0
  fi

  mapfile -t CANDIDATES < <(find "$TARGET_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'daml-stdlib-*' | sort)
  if [[ "${#CANDIDATES[@]}" -eq 0 ]]; then
    echo "No daml-stdlib source directory found under $TARGET_ROOT" >&2
    return 1
  fi

  for candidate in "${CANDIDATES[@]}"; do
    if [[ "$(basename -- "$candidate")" == "daml-stdlib-$SDK_VERSION"* ]]; then
      echo "$candidate"
      return 0
    fi
  done

  if [[ "${#CANDIDATES[@]}" -eq 1 ]]; then
    echo "${CANDIDATES[0]}"
    return 0
  fi

  echo "Multiple daml-stdlib source directories found under $TARGET_ROOT:" >&2
  printf '  %s\n' "${CANDIDATES[@]}" >&2
  return 1
}

generate_json_for_package() {
  local package_name="$1"
  local src_root="$2"
  local output_json="$3"
  local file_count
  local daml_files=()

  if [[ ! -d "$src_root" ]]; then
    echo "Source dir not found for package '$package_name': $src_root" >&2
    return 1
  fi

  mapfile -t daml_files < <(find "$src_root" -type f -name '*.daml' | sort)
  file_count="${#daml_files[@]}"
  if [[ "$file_count" -eq 0 ]]; then
    echo "No .daml files found under $src_root" >&2
    return 1
  fi

  log "Generating $package_name JSON"
  log "sdk=$SDK_VERSION lf_target=$LF_TARGET package=$package_name files=$file_count"
  dpm damlc docs \
    --output "$output_json" \
    --package-name "$package_name" \
    --format json \
    -Wno-deprecated-exceptions \
    --target "$LF_TARGET" \
    "${daml_files[@]}"
}

mkdir -p "$(dirname -- "$OUTPUT_JSON")"

PRIM_SRC_ROOT="$TARGET_ROOT/daml-prim"
STDLIB_SRC_ROOT=""

case "$PACKAGE_SET" in
  prim)
    generate_json_for_package "daml-prim" "$PRIM_SRC_ROOT" "$OUTPUT_JSON"
    ;;
  stdlib)
    STDLIB_SRC_ROOT="$(resolve_stdlib_src_root)"
    generate_json_for_package "daml-stdlib" "$STDLIB_SRC_ROOT" "$OUTPUT_JSON"
    ;;
  base)
    STDLIB_SRC_ROOT="$(resolve_stdlib_src_root)"
    TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/daml-base-json.XXXXXX")"
    trap 'rm -rf "$TMP_DIR"' EXIT
    PRIM_JSON="$TMP_DIR/daml-prim.json"
    STDLIB_JSON="$TMP_DIR/daml-stdlib.json"

    generate_json_for_package "daml-prim" "$PRIM_SRC_ROOT" "$PRIM_JSON"
    generate_json_for_package "daml-stdlib" "$STDLIB_SRC_ROOT" "$STDLIB_JSON"

    python3 - "$STDLIB_JSON" "$PRIM_JSON" "$OUTPUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

stdlib_path = Path(sys.argv[1])
prim_path = Path(sys.argv[2])
out_path = Path(sys.argv[3])

with stdlib_path.open("r", encoding="utf-8") as f:
    stdlib_modules = json.load(f)
with prim_path.open("r", encoding="utf-8") as f:
    prim_modules = json.load(f)

if not isinstance(stdlib_modules, list) or not isinstance(prim_modules, list):
    raise SystemExit("Expected list JSON payloads for stdlib and prim.")

combined = []
seen = set()
for module in stdlib_modules + prim_modules:
    if not isinstance(module, dict):
        continue
    name = module.get("md_name")
    if isinstance(name, str) and name in seen:
        continue
    if isinstance(name, str):
        seen.add(name)
    combined.append(module)

out_path.write_text(json.dumps(combined, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Combined modules: {len(combined)} (stdlib={len(stdlib_modules)}, prim={len(prim_modules)})")
PY
    ;;
esac

log "Wrote $OUTPUT_JSON"
