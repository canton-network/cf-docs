#!/usr/bin/env bash
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: sync_daml_prim_api_from_dpm.sh [options]

Generate Daml Prim API docs for multiple SDK versions and update docs.json.

Defaults:
- Select latest 3 stable SDK versions from `dpm version --all -o json`
- Write versioned MDX output under docs-main/daml-reference/daml-prim-api/vX-Y-Z
- Update top-level docs.json dropdown "Daml Reference Docs" with group "Daml Prim API"
- Remove legacy "Generated API Reference" groups from "App Development"

Options:
  --input-json PATH                 Use existing JSON (single-version mode only).
  --output-dir PATH                 Output root for versioned docs.
                                   Default: docs-main/daml-reference/daml-prim-api
  --docs-json PATH                  docs.json path. Default: docs.json
  --nav-base PATH                   docs.json page prefix. Default: output-dir

  --latest-n N                      Number of latest stable SDK versions. Default: 3
  --versions CSV                    Explicit SDK versions (comma-separated), highest priority.
  --sdk-version VER                 Single SDK version override (legacy option).
  --lf-target VER                   Forwarded to JSON generation.
  --dpm-home PATH                   Forwarded to JSON generation.
  --skip-install                    Forwarded to JSON generation.
  --keep-generated-json             Keep generated JSON temp directory and print its path.
  -h, --help                        Show this help.

Examples:
  ./scripts/sync_daml_prim_api_from_dpm.sh
  ./scripts/sync_daml_prim_api_from_dpm.sh --latest-n 3 --lf-target 2.2
  ./scripts/sync_daml_prim_api_from_dpm.sh --versions 3.4.11,3.4.10,3.4.9
  ./scripts/sync_daml_prim_api_from_dpm.sh --sdk-version 3.4.10 --input-json /tmp/daml-prim.json
USAGE
}

log() {
  printf '[daml-prim-sync] %s\n' "$*"
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

INPUT_JSON=""
OUTPUT_DIR="docs-main/daml-reference/daml-prim-api"
DOCS_JSON="docs.json"
NAV_BASE=""
KEEP_GENERATED_JSON=false

LATEST_N=3
VERSIONS_CSV=""
SDK_VERSION=""
LF_TARGET=""
DPM_HOME_OVERRIDE=""
SKIP_INSTALL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-json)
      INPUT_JSON="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --docs-json)
      DOCS_JSON="$2"
      shift 2
      ;;
    --nav-base)
      NAV_BASE="$2"
      shift 2
      ;;
    --latest-n)
      LATEST_N="$2"
      shift 2
      ;;
    --versions)
      VERSIONS_CSV="$2"
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
      DPM_HOME_OVERRIDE="$2"
      shift 2
      ;;
    --skip-install)
      SKIP_INSTALL=true
      shift
      ;;
    --keep-generated-json)
      KEEP_GENERATED_JSON=true
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

if [[ "$OUTPUT_DIR" != /* ]]; then
  OUTPUT_DIR="$REPO_ROOT/$OUTPUT_DIR"
fi
if [[ "$DOCS_JSON" != /* ]]; then
  DOCS_JSON="$REPO_ROOT/$DOCS_JSON"
fi
if [[ -n "$INPUT_JSON" && "$INPUT_JSON" != /* ]]; then
  INPUT_JSON="$REPO_ROOT/$INPUT_JSON"
fi
if [[ -z "$NAV_BASE" ]]; then
  NAV_BASE="$(python3 "$SCRIPT_DIR/relative_posix_path.py" "$OUTPUT_DIR" "$REPO_ROOT")"
fi

if [[ ! -f "$DOCS_JSON" ]]; then
  echo "docs.json not found: $DOCS_JSON" >&2
  exit 1
fi

TARGET_VERSIONS=()
if [[ -n "$VERSIONS_CSV" ]]; then
  IFS=',' read -r -a raw_versions <<<"$VERSIONS_CSV"
  for v in "${raw_versions[@]}"; do
    vv="$(echo "$v" | xargs)"
    if [[ -n "$vv" ]]; then
      TARGET_VERSIONS+=("$vv")
    fi
  done
elif [[ -n "$SDK_VERSION" && "$SDK_VERSION" != "latest" ]]; then
  TARGET_VERSIONS=("$SDK_VERSION")
else
  mapfile -t TARGET_VERSIONS < <(python3 "$SCRIPT_DIR/list_latest_stable_dpm_versions.py" "$LATEST_N")
fi

DEDUPED_TARGET_VERSIONS=()
declare -A _seen_versions=()
for _version in "${TARGET_VERSIONS[@]}"; do
  if [[ -z "${_seen_versions[$_version]+x}" ]]; then
    DEDUPED_TARGET_VERSIONS+=("$_version")
    _seen_versions[$_version]=1
  fi
done
TARGET_VERSIONS=("${DEDUPED_TARGET_VERSIONS[@]}")

if [[ "${#TARGET_VERSIONS[@]}" -eq 0 ]]; then
  echo "No target SDK versions resolved." >&2
  exit 1
fi

if [[ -n "$INPUT_JSON" ]]; then
  if [[ ! -f "$INPUT_JSON" ]]; then
    echo "Input JSON not found: $INPUT_JSON" >&2
    exit 1
  fi
  if [[ "${#TARGET_VERSIONS[@]}" -ne 1 ]]; then
    echo "--input-json is only supported with a single target version." >&2
    exit 1
  fi
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/daml-prim-json.XXXXXX")"
VERSIONS_ENTRIES_JSONL="$TMP_DIR/version-entries.jsonl"
if [[ "$KEEP_GENERATED_JSON" == false ]]; then
  trap 'rm -rf "$TMP_DIR"' EXIT
fi

mkdir -p "$OUTPUT_DIR"
touch "$VERSIONS_ENTRIES_JSONL"

log "Target SDK versions: ${TARGET_VERSIONS[*]}"
for SDK_VER in "${TARGET_VERSIONS[@]}"; do
  VERSION_SLUG="v${SDK_VER//./-}"
  VERSION_OUTPUT_DIR="$OUTPUT_DIR/$VERSION_SLUG"
  VERSION_NAV_BASE="${NAV_BASE%/}/$VERSION_SLUG"

  JSON_PATH="$INPUT_JSON"
  if [[ -z "$JSON_PATH" ]]; then
    JSON_PATH="$TMP_DIR/daml-prim-$SDK_VER.json"
    GEN_ARGS=(--output-json "$JSON_PATH" --sdk-version "$SDK_VER")
    if [[ -n "$LF_TARGET" ]]; then
      GEN_ARGS+=(--lf-target "$LF_TARGET")
    fi
    if [[ -n "$DPM_HOME_OVERRIDE" ]]; then
      GEN_ARGS+=(--dpm-home "$DPM_HOME_OVERRIDE")
    fi
    if [[ "$SKIP_INSTALL" == true ]]; then
      GEN_ARGS+=(--skip-install)
    fi
    "$SCRIPT_DIR/generate_daml_prim_json_from_dpm.sh" "${GEN_ARGS[@]}"
  fi

  log "Converting JSON to MDX for SDK $SDK_VER"
  python3 "$SCRIPT_DIR/daml_docs_json_to_mdx.py" \
    --input-json "$JSON_PATH" \
    --output-dir "$VERSION_OUTPUT_DIR"

  python3 "$SCRIPT_DIR/append_version_nav_entry.py" \
    --version "$SDK_VER" \
    --nav-base "$VERSION_NAV_BASE" \
    --output-dir "$VERSION_OUTPUT_DIR" \
    --entries-jsonl "$VERSIONS_ENTRIES_JSONL"
done

log "Updating docs.json navigation"
python3 "$SCRIPT_DIR/update_daml_reference_docs_from_entries.py" \
  --docs-json "$DOCS_JSON" \
  --entries-jsonl "$VERSIONS_ENTRIES_JSONL"

if [[ "$KEEP_GENERATED_JSON" == true ]]; then
  log "Generated JSON kept under: $TMP_DIR"
fi
