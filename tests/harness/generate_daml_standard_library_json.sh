#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: generate_daml_standard_library_json.sh --output-json PATH [options]

Generate Daml Standard Library docs JSON using installed SDK artifacts.

Options:
  --output-json PATH   Destination JSON file path. (required)
  --sdk-version VER    SDK version to use. Default: latest stable from get.digitalasset.com.
  --lf-target VER      LF target folder (e.g. 2.2). Default: highest numeric target available.
  --package-set SET    One of: prim, stdlib, base. Default: base.
  --sdk-source SRC     One of: auto, daml, dpm. Default: dpm.
  --daml-home PATH     DAML home dir. Default: $DAML_HOME or ~/.daml
  --dpm-home PATH      DPM home dir. Default: $DPM_HOME or ~/.dpm
  --skip-install       Skip installing missing SDK for selected source.
  -h, --help           Show this help.
USAGE
}

log() {
  printf '[daml-stdlib-json] %s\n' "$*"
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
PACKAGE_SET="${DAML_DOCS_PACKAGE_SET:-base}"
SDK_SOURCE="${DAML_DOCS_SDK_SOURCE:-dpm}"
DAML_HOME_DIR="${DAML_HOME:-$HOME/.daml}"
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
    --sdk-source)
      SDK_SOURCE="$2"
      shift 2
      ;;
    --daml-home)
      DAML_HOME_DIR="$2"
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
require_arg "--package-set" "$PACKAGE_SET"

if [[ "$SDK_VERSION" == "latest" ]]; then
  SDK_VERSION="$(latest_sdk_version)"
fi
require_arg "--sdk-version" "$SDK_VERSION"

daml_pkg_db_root() {
  printf '%s\n' "$DAML_HOME_DIR/sdk/$SDK_VERSION/damlc/resources/pkg-db_dir"
}

dpm_pkg_db_root() {
  printf '%s\n' "$DPM_HOME_DIR/cache/components/damlc/$SDK_VERSION/damlc-dist-dpm/resources/pkg-db_dir"
}

dpm_damlc_bin() {
  printf '%s\n' "$DPM_HOME_DIR/cache/components/damlc/$SDK_VERSION/damlc-dist-dpm/damlc"
}

ensure_daml_sdk() {
  local pkg_db_root
  pkg_db_root="$(daml_pkg_db_root)"
  if [[ -d "$pkg_db_root" ]]; then
    return 0
  fi
  if [[ "$SKIP_INSTALL" == true ]]; then
    echo "DAML SDK not found at $pkg_db_root and --skip-install was set." >&2
    return 1
  fi
  daml install "$SDK_VERSION" --quiet
  [[ -d "$pkg_db_root" ]]
}

ensure_dpm_sdk() {
  local pkg_db_root
  pkg_db_root="$(dpm_pkg_db_root)"
  if [[ -d "$pkg_db_root" ]]; then
    return 0
  fi
  if [[ "$SKIP_INSTALL" == true ]]; then
    echo "DPM SDK cache not found at $pkg_db_root and --skip-install was set." >&2
    return 1
  fi
  dpm install "$SDK_VERSION"
  [[ -d "$pkg_db_root" ]]
}

if [[ "$SDK_SOURCE" == "auto" ]]; then
  if [[ -d "$(dpm_pkg_db_root)" ]]; then
    SDK_SOURCE="dpm"
  elif [[ -d "$(daml_pkg_db_root)" ]]; then
    SDK_SOURCE="daml"
  elif command -v dpm >/dev/null 2>&1; then
    SDK_SOURCE="dpm"
  else
    SDK_SOURCE="daml"
  fi
fi

PKG_DB_ROOT=""
DOCS_CMD=()

configure_daml_source() {
  ensure_daml_sdk
  PKG_DB_ROOT="$(daml_pkg_db_root)"
  DOCS_CMD=("$DAML_HOME_DIR/sdk/$SDK_VERSION/damlc/damlc" "docs")
}

configure_dpm_source() {
  ensure_dpm_sdk
  PKG_DB_ROOT="$(dpm_pkg_db_root)"
  DPM_DAMLC_BIN="$(dpm_damlc_bin)"
  if [[ ! -x "$DPM_DAMLC_BIN" ]]; then
    echo "DPM damlc binary not found: $DPM_DAMLC_BIN" >&2
    return 1
  fi
  DOCS_CMD=("$DPM_DAMLC_BIN" "docs")
}

case "$SDK_SOURCE" in
  daml)
    configure_daml_source || configure_dpm_source
    ;;
  dpm)
    configure_dpm_source || configure_daml_source
    ;;
esac

if [[ ! -d "$PKG_DB_ROOT" ]]; then
  echo "Package DB root not found: $PKG_DB_ROOT" >&2
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
  log "source=$SDK_SOURCE sdk=$SDK_VERSION lf_target=$LF_TARGET package=$package_name files=$file_count"
  "${DOCS_CMD[@]}" \
    --output "$output_json" \
    --package-name "$package_name" \
    --format json \
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

    # Merge same md_name modules (Prelude / DA.Exception / DA.Stack MOVE collisions)
    # instead of first-wins, which dropped daml-prim MOVE content.
    python3 "$SCRIPT_DIR/../../scripts/merge_daml_docs_modules.py" "$STDLIB_JSON" "$PRIM_JSON" "$OUTPUT_JSON"
    ;;
esac

log "Wrote $OUTPUT_JSON"
