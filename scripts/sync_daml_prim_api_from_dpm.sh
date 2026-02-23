#!/usr/bin/env bash
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: sync_daml_prim_api_from_dpm.sh [options]

Generate daml-prim JSON from dpm SDK artifacts and convert it to MDX docs.

Options:
  --input-json PATH                 Use existing JSON file instead of generating one.
  --output-dir PATH                 MDX output directory. Default: docs-main/appdev/reference/daml-prim-api
  --docs-json PATH                  docs.json path. Default: docs.json
  --nav-group-name NAME             docs.json group name. Default: Generated API Reference
  --nav-base PATH                   docs.json page prefix. Default: output-dir
  --nav-dropdown-name NAME          Scope nav updates under this dropdown. Default: App Development
  --create-nav-group-if-missing     Insert group if missing (default).
  --no-create-nav-group-if-missing  Require group to already exist.

  --sdk-version VER                 Forwarded to JSON generation.
  --lf-target VER                   Forwarded to JSON generation.
  --dpm-home PATH                   Forwarded to JSON generation.
  --skip-install                    Forwarded to JSON generation.
  --keep-generated-json             Keep generated JSON in a temp directory and print its path.
  -h, --help                        Show this help.

Examples:
  ./scripts/sync_daml_prim_api_from_dpm.sh --sdk-version 3.4.10 --lf-target 2.2
  ./scripts/sync_daml_prim_api_from_dpm.sh --input-json /tmp/daml-prim.json
USAGE
}

log() {
  printf '[daml-prim-sync] %s\n' "$*"
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

INPUT_JSON=""
OUTPUT_DIR="docs-main/appdev/reference/daml-prim-api"
DOCS_JSON="docs.json"
NAV_GROUP_NAME="Generated API Reference"
NAV_BASE=""
NAV_DROPDOWN_NAME="App Development"
CREATE_NAV_GROUP_IF_MISSING=true
KEEP_GENERATED_JSON=false

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
    --nav-group-name)
      NAV_GROUP_NAME="$2"
      shift 2
      ;;
    --nav-base)
      NAV_BASE="$2"
      shift 2
      ;;
    --nav-dropdown-name)
      NAV_DROPDOWN_NAME="$2"
      shift 2
      ;;
    --create-nav-group-if-missing)
      CREATE_NAV_GROUP_IF_MISSING=true
      shift
      ;;
    --no-create-nav-group-if-missing)
      CREATE_NAV_GROUP_IF_MISSING=false
      shift
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
  NAV_BASE="$(python3 -c "import os; print(os.path.relpath('$OUTPUT_DIR', '$REPO_ROOT').replace(os.sep, '/'))")"
fi

if [[ ! -f "$DOCS_JSON" ]]; then
  echo "docs.json not found: $DOCS_JSON" >&2
  exit 1
fi

GENERATED_JSON=""
if [[ -z "$INPUT_JSON" ]]; then
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/daml-prim-json.XXXXXX")"
  GENERATED_JSON="$TMP_DIR/daml-prim.json"
  if [[ "$KEEP_GENERATED_JSON" == false ]]; then
    trap 'rm -rf "$TMP_DIR"' EXIT
  fi

  GEN_ARGS=(--output-json "$GENERATED_JSON")
  if [[ -n "$SDK_VERSION" ]]; then
    GEN_ARGS+=(--sdk-version "$SDK_VERSION")
  fi
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
  INPUT_JSON="$GENERATED_JSON"
else
  if [[ ! -f "$INPUT_JSON" ]]; then
    echo "Input JSON not found: $INPUT_JSON" >&2
    exit 1
  fi
fi

CONVERTER_ARGS=(
  --input-json "$INPUT_JSON"
  --output-dir "$OUTPUT_DIR"
  --docs-json "$DOCS_JSON"
  --nav-group-name "$NAV_GROUP_NAME"
  --nav-base "$NAV_BASE"
  --nav-dropdown-name "$NAV_DROPDOWN_NAME"
)
if [[ "$CREATE_NAV_GROUP_IF_MISSING" == true ]]; then
  CONVERTER_ARGS+=(--create-nav-group-if-missing)
fi

log "Running JSON -> MDX conversion"
python3 "$SCRIPT_DIR/daml_docs_json_to_mdx.py" "${CONVERTER_ARGS[@]}"

if [[ -n "$GENERATED_JSON" && "$KEEP_GENERATED_JSON" == true ]]; then
  log "Generated JSON kept at: $GENERATED_JSON"
fi
