#!/usr/bin/env bash
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Shared SDK resolution helpers for damlc docs JSON extraction scripts.
# Source this file, set the DAML_DOCS_* variables below, then call daml_docs_sdk_configure.

: "${DAML_DOCS_SCRIPT_DIR:?DAML_DOCS_SCRIPT_DIR must be set before sourcing daml_docs_sdk.sh}"

daml_docs_log() {
  printf '[daml-docs-json] %s\n' "$*"
}

daml_docs_require_arg() {
  local flag="$1"
  local value="${2:-}"
  if [[ -z "$value" ]]; then
    echo "Missing value for $flag" >&2
    return 1
  fi
}

daml_docs_latest_sdk_version() {
  curl -fsSL "https://get.digitalasset.com/install/latest"
}

daml_docs_daml_pkg_db_root() {
  printf '%s\n' "$DAML_DOCS_DAML_HOME/sdk/$DAML_DOCS_SDK_VERSION/damlc/resources/pkg-db_dir"
}

daml_docs_dpm_pkg_db_root() {
  printf '%s\n' "$DAML_DOCS_DPM_HOME/cache/components/damlc/$DAML_DOCS_SDK_VERSION/damlc-dist-dpm/resources/pkg-db_dir"
}

daml_docs_dpm_damlc_bin() {
  printf '%s\n' "$DAML_DOCS_DPM_HOME/cache/components/damlc/$DAML_DOCS_SDK_VERSION/damlc-dist-dpm/damlc"
}

daml_docs_ensure_daml_sdk() {
  local pkg_db_root
  pkg_db_root="$(daml_docs_daml_pkg_db_root)"
  if [[ -d "$pkg_db_root" ]]; then
    return 0
  fi
  if [[ "$DAML_DOCS_SKIP_INSTALL" == true ]]; then
    echo "DAML SDK not found at $pkg_db_root and --skip-install was set." >&2
    return 1
  fi
  if ! command -v daml >/dev/null 2>&1; then
    echo "daml not found in PATH." >&2
    return 1
  fi
  daml_docs_log "Installing SDK ${DAML_DOCS_SDK_VERSION} via daml"
  if ! daml install "$DAML_DOCS_SDK_VERSION" --quiet; then
    echo "Failed to install SDK ${DAML_DOCS_SDK_VERSION} via daml." >&2
    return 1
  fi
  if [[ ! -d "$pkg_db_root" ]]; then
    echo "DAML SDK package DB root not found after install: $pkg_db_root" >&2
    return 1
  fi
  return 0
}

daml_docs_ensure_dpm_sdk() {
  local pkg_db_root
  pkg_db_root="$(daml_docs_dpm_pkg_db_root)"
  if [[ -d "$pkg_db_root" ]]; then
    return 0
  fi
  if [[ "$DAML_DOCS_SKIP_INSTALL" == true ]]; then
    echo "DPM SDK cache not found at $pkg_db_root and --skip-install was set." >&2
    return 1
  fi
  if ! command -v dpm >/dev/null 2>&1; then
    echo "dpm not found in PATH." >&2
    return 1
  fi
  daml_docs_log "Installing SDK ${DAML_DOCS_SDK_VERSION} via dpm"
  if ! dpm install "$DAML_DOCS_SDK_VERSION"; then
    echo "Failed to install SDK ${DAML_DOCS_SDK_VERSION} via dpm." >&2
    return 1
  fi
  if [[ ! -d "$pkg_db_root" ]]; then
    echo "DPM package DB root not found after install: $pkg_db_root" >&2
    return 1
  fi
  return 0
}

daml_docs_configure_daml_source() {
  if ! daml_docs_ensure_daml_sdk; then
    return 1
  fi
  DAML_DOCS_PKG_DB_ROOT="$(daml_docs_daml_pkg_db_root)"
  local daml_damlc_bin="$DAML_DOCS_DAML_HOME/sdk/$DAML_DOCS_SDK_VERSION/damlc/damlc"
  if [[ ! -x "$daml_damlc_bin" ]]; then
    echo "damlc binary not found: $daml_damlc_bin" >&2
    return 1
  fi
  DAML_DOCS_DOCS_CMD=("$daml_damlc_bin" "docs")
  DAML_DOCS_SDK_SOURCE="daml"
  return 0
}

daml_docs_configure_dpm_source() {
  if ! daml_docs_ensure_dpm_sdk; then
    return 1
  fi
  DAML_DOCS_PKG_DB_ROOT="$(daml_docs_dpm_pkg_db_root)"
  local dpm_damlc_bin
  dpm_damlc_bin="$(daml_docs_dpm_damlc_bin)"
  if [[ ! -x "$dpm_damlc_bin" ]]; then
    echo "DPM damlc binary not found: $dpm_damlc_bin" >&2
    return 1
  fi
  DAML_DOCS_DOCS_CMD=("$dpm_damlc_bin" "docs")
  DAML_DOCS_SDK_SOURCE="dpm"
  return 0
}

daml_docs_sdk_configure() {
  if [[ "$DAML_DOCS_SDK_VERSION" == "latest" ]]; then
    DAML_DOCS_SDK_VERSION="$(daml_docs_latest_sdk_version)"
  fi
  if ! daml_docs_require_arg "--sdk-version" "$DAML_DOCS_SDK_VERSION"; then
    return 1
  fi

  if [[ "$DAML_DOCS_SDK_SOURCE" == "auto" ]]; then
    if [[ -d "$(daml_docs_dpm_pkg_db_root)" ]]; then
      DAML_DOCS_SDK_SOURCE="dpm"
    elif [[ -d "$(daml_docs_daml_pkg_db_root)" ]]; then
      DAML_DOCS_SDK_SOURCE="daml"
    elif command -v dpm >/dev/null 2>&1; then
      DAML_DOCS_SDK_SOURCE="dpm"
    elif command -v daml >/dev/null 2>&1; then
      DAML_DOCS_SDK_SOURCE="daml"
    else
      echo "Neither daml nor dpm is available and no SDK cache was found." >&2
      return 1
    fi
  fi

  case "$DAML_DOCS_SDK_SOURCE" in
    daml)
      if ! daml_docs_configure_daml_source; then
        daml_docs_log "Falling back to dpm for SDK ${DAML_DOCS_SDK_VERSION}"
        if ! daml_docs_configure_dpm_source; then
          echo "Failed to resolve SDK ${DAML_DOCS_SDK_VERSION} via daml or dpm." >&2
          return 1
        fi
      fi
      ;;
    dpm)
      if ! daml_docs_configure_dpm_source; then
        daml_docs_log "Falling back to daml for SDK ${DAML_DOCS_SDK_VERSION}"
        if ! daml_docs_configure_daml_source; then
          echo "Failed to resolve SDK ${DAML_DOCS_SDK_VERSION} via dpm or daml." >&2
          return 1
        fi
      fi
      ;;
    *)
      echo "Invalid sdk source '$DAML_DOCS_SDK_SOURCE'. Expected one of: auto, daml, dpm." >&2
      return 1
      ;;
  esac

  if [[ ! -d "$DAML_DOCS_PKG_DB_ROOT" ]]; then
    echo "Package DB root not found: $DAML_DOCS_PKG_DB_ROOT" >&2
    return 1
  fi

  if [[ -z "$DAML_DOCS_LF_TARGET" ]]; then
    DAML_DOCS_LF_TARGET="$(python3 "$DAML_DOCS_SCRIPT_DIR/select_latest_lf_target.py" "$DAML_DOCS_PKG_DB_ROOT")"
  fi
  if ! daml_docs_require_arg "--lf-target" "$DAML_DOCS_LF_TARGET"; then
    return 1
  fi

  DAML_DOCS_TARGET_ROOT="$DAML_DOCS_PKG_DB_ROOT/$DAML_DOCS_LF_TARGET"
  if [[ ! -d "$DAML_DOCS_TARGET_ROOT" ]]; then
    echo "LF target root not found: $DAML_DOCS_TARGET_ROOT" >&2
    echo "Available LF targets under $DAML_DOCS_PKG_DB_ROOT:" >&2
    find "$DAML_DOCS_PKG_DB_ROOT" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort >&2 || true
    return 1
  fi

  return 0
}
