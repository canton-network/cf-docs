#!/usr/bin/env bash
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: generate_daml_standard_library_json.sh --output-json PATH [options]

Generate Daml Standard Library docs JSON using installed SDK artifacts.

SDK source selection:
- dpm (default): use DPM cache + cached damlc binary.
- auto: prefer DPM cache under ~/.dpm, fallback to DAML SDK installation
  under ~/.daml/sdk/<version>.
- daml: use DAML SDK layout + damlc binary.

Options:
  --output-json PATH   Destination JSON file path. (required)
  --sdk-version VER    SDK version to use. Default: latest stable from get.digitalasset.com.
  --lf-target VER      LF target folder (e.g. 2.2). Default: highest numeric target available.
  --package-set SET    One of: prim, stdlib, base. Default: base.
                       - prim:   only daml-prim modules
                       - stdlib: only daml-stdlib modules
                       - base:   stdlib + prim merged (matches docs pipeline composition)
  --sdk-source SRC     One of: auto, daml, dpm. Default: dpm.
  --daml-home PATH     DAML home dir. Default: $DAML_HOME or ~/.daml
  --dpm-home PATH      DPM home dir. Default: $DPM_HOME or ~/.dpm
  --skip-install       Skip installing missing SDK for selected source.
  -h, --help           Show this help.

Environment:
  DAML_DOCS_SDK_VERSION  Default for --sdk-version.
  DAML_DOCS_LF_TARGET    Default for --lf-target.
  DAML_DOCS_PACKAGE_SET  Default for --package-set.
  DAML_DOCS_SDK_SOURCE   Default for --sdk-source.
  DAML_HOME              Default for --daml-home.
  DPM_HOME               Default for --dpm-home.

Example:
  ./scripts/generate_daml_standard_library_json.sh \
    --output-json /tmp/daml-base.json \
    --sdk-version 3.3.0-snapshot.20250930.0 \
    --lf-target 2.1 \
    --package-set base \
    --sdk-source dpm
USAGE
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

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
DAML_DOCS_SCRIPT_DIR="$SCRIPT_DIR"
# shellcheck source=lib/daml_docs_sdk.sh
source "$SCRIPT_DIR/lib/daml_docs_sdk.sh"

OUTPUT_JSON=""
DAML_DOCS_SDK_VERSION="${DAML_DOCS_SDK_VERSION:-latest}"
DAML_DOCS_LF_TARGET="${DAML_DOCS_LF_TARGET:-}"
PACKAGE_SET="${DAML_DOCS_PACKAGE_SET:-base}"
DAML_DOCS_SDK_SOURCE="${DAML_DOCS_SDK_SOURCE:-dpm}"
DAML_DOCS_DAML_HOME="${DAML_HOME:-$HOME/.daml}"
DAML_DOCS_DPM_HOME="${DPM_HOME:-$HOME/.dpm}"
DAML_DOCS_SKIP_INSTALL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-json)
      OUTPUT_JSON="$2"
      shift 2
      ;;
    --sdk-version)
      DAML_DOCS_SDK_VERSION="$2"
      shift 2
      ;;
    --lf-target)
      DAML_DOCS_LF_TARGET="$2"
      shift 2
      ;;
    --package-set)
      PACKAGE_SET="$2"
      shift 2
      ;;
    --sdk-source)
      DAML_DOCS_SDK_SOURCE="$2"
      shift 2
      ;;
    --daml-home)
      DAML_DOCS_DAML_HOME="$2"
      shift 2
      ;;
    --dpm-home)
      DAML_DOCS_DPM_HOME="$2"
      shift 2
      ;;
    --skip-install)
      DAML_DOCS_SKIP_INSTALL=true
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
require_arg "--package-set" "$PACKAGE_SET"
if [[ "$PACKAGE_SET" != "prim" && "$PACKAGE_SET" != "stdlib" && "$PACKAGE_SET" != "base" ]]; then
  echo "Invalid --package-set '$PACKAGE_SET'. Expected one of: prim, stdlib, base." >&2
  exit 1
fi
if [[ "$DAML_DOCS_SDK_SOURCE" != "auto" && "$DAML_DOCS_SDK_SOURCE" != "daml" && "$DAML_DOCS_SDK_SOURCE" != "dpm" ]]; then
  echo "Invalid --sdk-source '$DAML_DOCS_SDK_SOURCE'. Expected one of: auto, daml, dpm." >&2
  exit 1
fi

daml_docs_sdk_configure

resolve_stdlib_src_root() {
  local candidate
  candidate="$DAML_DOCS_TARGET_ROOT/daml-stdlib-$DAML_DOCS_SDK_VERSION"
  if [[ -d "$candidate" ]]; then
    echo "$candidate"
    return 0
  fi

  mapfile -t CANDIDATES < <(find "$DAML_DOCS_TARGET_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'daml-stdlib-*' | sort)
  if [[ "${#CANDIDATES[@]}" -eq 0 ]]; then
    echo "No daml-stdlib source directory found under $DAML_DOCS_TARGET_ROOT" >&2
    return 1
  fi

  for candidate in "${CANDIDATES[@]}"; do
    if [[ "$(basename -- "$candidate")" == "daml-stdlib-$DAML_DOCS_SDK_VERSION"* ]]; then
      echo "$candidate"
      return 0
    fi
  done

  if [[ "${#CANDIDATES[@]}" -eq 1 ]]; then
    echo "${CANDIDATES[0]}"
    return 0
  fi

  echo "Multiple daml-stdlib source directories found under $DAML_DOCS_TARGET_ROOT:" >&2
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

  daml_docs_log "Generating $package_name JSON"
  daml_docs_log "source=$DAML_DOCS_SDK_SOURCE sdk=$DAML_DOCS_SDK_VERSION lf_target=$DAML_DOCS_LF_TARGET package=$package_name files=$file_count"
  "${DAML_DOCS_DOCS_CMD[@]}" \
    --output "$output_json" \
    --package-name "$package_name" \
    --format json \
    --target "$DAML_DOCS_LF_TARGET" \
    "${daml_files[@]}"
}

mkdir -p "$(dirname -- "$OUTPUT_JSON")"

PRIM_SRC_ROOT="$DAML_DOCS_TARGET_ROOT/daml-prim"
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

    # Merge same md_name modules (Prelude / DA.Exception / DA.Stack MOVE collisions)
    # instead of first-wins, which dropped daml-prim MOVE content.
    python3 "$SCRIPT_DIR/merge_daml_docs_modules.py" "$STDLIB_JSON" "$PRIM_JSON" "$OUTPUT_JSON"
    ;;
esac

daml_docs_log "Wrote $OUTPUT_JSON"
