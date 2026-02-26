#!/usr/bin/env bash
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: sync_daml_prim_api_from_dpm.sh [options]

Generate Daml Standard Library docs from published SDK artifacts.

Behavior:
- Analyze multiple SDK versions (latest 3 per family by default) to enrich published pages
  (for example: deprecation-first-seen metadata).
- Publish only one docs tree (latest by default) at docs-main/daml-reference/daml-prim-api.
- Update docs.json under App Development group "Daml Standard Library"
  (no Daml Reference Docs version dropdown).

Options:
  --input-json PATH                 Use existing JSON as publish input (single-version mode only).
  --output-dir PATH                 Output root for published docs.
                                   Default: docs-main/daml-reference/daml-prim-api
  --docs-json PATH                  docs.json path. Default: docs.json
  --nav-base PATH                   docs.json page prefix. Default: output-dir relative to repo root

  --latest-n N                      Number of latest versions to analyze per family. Default: 3
  --minor-families CSV              Analyze families in priority order. Default: 3.4,3.3,3.2
  --versions CSV                    Explicit SDK versions to analyze (comma-separated), highest priority.
  --sdk-version VER                 SDK version to publish. If set (not latest), also used as analyze default.
  --publish-sdk-version VER         Explicit publish SDK version (must be analyzable/generated).
  --package-set SET                 Forwarded to JSON generation. One of: prim, stdlib, base.
                                   Default: base
  --sdk-source SRC                  Forwarded to JSON generation. One of: auto, daml, dpm.
                                   Default: dpm
  --lf-target VER                   Forwarded to JSON generation.
  --daml-home PATH                  Forwarded to JSON generation.
  --dpm-home PATH                   Forwarded to JSON generation.
  --skip-install                    Forwarded to JSON generation.
  --keep-generated-json             Keep generated JSON temp directory and print its path.
  -h, --help                        Show this help.

Examples:
  ./scripts/sync_daml_prim_api_from_dpm.sh
  ./scripts/sync_daml_prim_api_from_dpm.sh --latest-n 3 --minor-families 3.4,3.3,3.2 --lf-target 2.2
  ./scripts/sync_daml_prim_api_from_dpm.sh --versions 3.4.11,3.4.10,3.4.9
  ./scripts/sync_daml_prim_api_from_dpm.sh --versions 3.4.11,3.4.10,3.4.9 --publish-sdk-version 3.4.11
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
MINOR_FAMILIES="3.4,3.3,3.2"
VERSIONS_CSV=""
SDK_VERSION=""
PUBLISH_SDK_VERSION=""
LF_TARGET=""
SDK_SOURCE="dpm"
DAML_HOME_OVERRIDE=""
DPM_HOME_OVERRIDE=""
SKIP_INSTALL=false
PACKAGE_SET="base"

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
    --minor-families)
      MINOR_FAMILIES="$2"
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
    --publish-sdk-version)
      PUBLISH_SDK_VERSION="$2"
      shift 2
      ;;
    --lf-target)
      LF_TARGET="$2"
      shift 2
      ;;
    --sdk-source)
      SDK_SOURCE="$2"
      shift 2
      ;;
    --daml-home)
      DAML_HOME_OVERRIDE="$2"
      shift 2
      ;;
    --package-set)
      PACKAGE_SET="$2"
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

if [[ "$PACKAGE_SET" != "prim" && "$PACKAGE_SET" != "stdlib" && "$PACKAGE_SET" != "base" ]]; then
  echo "Invalid --package-set '$PACKAGE_SET'. Expected one of: prim, stdlib, base." >&2
  exit 1
fi
if [[ "$SDK_SOURCE" != "auto" && "$SDK_SOURCE" != "daml" && "$SDK_SOURCE" != "dpm" ]]; then
  echo "Invalid --sdk-source '$SDK_SOURCE'. Expected one of: auto, daml, dpm." >&2
  exit 1
fi

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
if [[ -n "$INPUT_JSON" && ! -f "$INPUT_JSON" ]]; then
  echo "Input JSON not found: $INPUT_JSON" >&2
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
  mapfile -t TARGET_VERSIONS < <(
    python3 "$SCRIPT_DIR/list_latest_release_versions_by_family.py" \
      "$LATEST_N" \
      --families "$MINOR_FAMILIES"
  )
fi

# Deduplicate while preserving order.
DEDUPED_TARGET_VERSIONS=()
declare -A _seen_versions=()
for _version in "${TARGET_VERSIONS[@]}"; do
  if [[ -z "${_seen_versions[$_version]+x}" ]]; then
    DEDUPED_TARGET_VERSIONS+=("$_version")
    _seen_versions[$_version]=1
  fi
done
TARGET_VERSIONS=("${DEDUPED_TARGET_VERSIONS[@]}")

if [[ "${#TARGET_VERSIONS[@]}" -eq 0 && -z "$INPUT_JSON" ]]; then
  echo "No target SDK versions resolved." >&2
  exit 1
fi

if [[ -z "$PUBLISH_SDK_VERSION" ]]; then
  if [[ -n "$SDK_VERSION" && "$SDK_VERSION" != "latest" ]]; then
    PUBLISH_SDK_VERSION="$SDK_VERSION"
  elif [[ "${#TARGET_VERSIONS[@]}" -gt 0 ]]; then
    PUBLISH_SDK_VERSION="${TARGET_VERSIONS[0]}"
  else
    PUBLISH_SDK_VERSION="input-json"
  fi
fi

if [[ -n "$INPUT_JSON" ]]; then
  if [[ -n "$VERSIONS_CSV" && "${#TARGET_VERSIONS[@]}" -gt 1 ]]; then
    echo "--input-json cannot be combined with multiple analyze versions." >&2
    exit 1
  fi
  TARGET_VERSIONS=("$PUBLISH_SDK_VERSION")
else
  if [[ -n "$PUBLISH_SDK_VERSION" && "$PUBLISH_SDK_VERSION" != "input-json" ]]; then
    in_targets=false
    for _version in "${TARGET_VERSIONS[@]}"; do
      if [[ "$_version" == "$PUBLISH_SDK_VERSION" ]]; then
        in_targets=true
        break
      fi
    done
    if [[ "$in_targets" == false ]]; then
      TARGET_VERSIONS=("$PUBLISH_SDK_VERSION" "${TARGET_VERSIONS[@]}")
    fi
  fi
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/daml-prim-json.XXXXXX")"
GENERATED_VERSIONS_TSV="$TMP_DIR/generated-versions.tsv"
if [[ "$KEEP_GENERATED_JSON" == false ]]; then
  trap 'rm -rf "$TMP_DIR"' EXIT
fi

touch "$GENERATED_VERSIONS_TSV"

log "Analyze SDK versions: ${TARGET_VERSIONS[*]}"
for SDK_VER in "${TARGET_VERSIONS[@]}"; do
  JSON_PATH="$INPUT_JSON"
  if [[ -z "$JSON_PATH" ]]; then
    JSON_PATH="$TMP_DIR/daml-prim-$SDK_VER.json"
    GEN_ARGS=(--output-json "$JSON_PATH" --sdk-version "$SDK_VER")
    GEN_ARGS+=(--package-set "$PACKAGE_SET")
    GEN_ARGS+=(--sdk-source "$SDK_SOURCE")
    if [[ -n "$LF_TARGET" ]]; then
      GEN_ARGS+=(--lf-target "$LF_TARGET")
    fi
    if [[ -n "$DAML_HOME_OVERRIDE" ]]; then
      GEN_ARGS+=(--daml-home "$DAML_HOME_OVERRIDE")
    fi
    if [[ -n "$DPM_HOME_OVERRIDE" ]]; then
      GEN_ARGS+=(--dpm-home "$DPM_HOME_OVERRIDE")
    fi
    if [[ "$SKIP_INSTALL" == true ]]; then
      GEN_ARGS+=(--skip-install)
    fi
    "$SCRIPT_DIR/generate_daml_prim_json_from_dpm.sh" "${GEN_ARGS[@]}"
  fi

  printf '%s\t%s\n' \
    "$SDK_VER" \
    "$JSON_PATH" >>"$GENERATED_VERSIONS_TSV"
done

DEPRECATION_FIRST_SEEN_JSON="$TMP_DIR/module-deprecation-first-seen.json"
VERSION_JSON_ARGS=()
while IFS=$'\t' read -r SDK_VER JSON_PATH; do
  if [[ -z "$SDK_VER" || -z "$JSON_PATH" ]]; then
    continue
  fi
  VERSION_JSON_ARGS+=(--version-json "$SDK_VER=$JSON_PATH")
done <"$GENERATED_VERSIONS_TSV"

if [[ "${#VERSION_JSON_ARGS[@]}" -gt 0 ]]; then
  log "Computing module deprecation first-seen map"
  python3 "$SCRIPT_DIR/compute_module_deprecation_first_seen.py" \
    "${VERSION_JSON_ARGS[@]}" \
    --output-json "$DEPRECATION_FIRST_SEEN_JSON"
fi

PUBLISH_JSON_PATH=""
while IFS=$'\t' read -r SDK_VER JSON_PATH; do
  if [[ "$SDK_VER" == "$PUBLISH_SDK_VERSION" ]]; then
    PUBLISH_JSON_PATH="$JSON_PATH"
    break
  fi
done <"$GENERATED_VERSIONS_TSV"

if [[ -z "$PUBLISH_JSON_PATH" ]]; then
  echo "Failed to resolve publish JSON for SDK version: $PUBLISH_SDK_VERSION" >&2
  exit 1
fi

log "Publishing SDK version: $PUBLISH_SDK_VERSION"
log "Publish JSON: $PUBLISH_JSON_PATH"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

python3 "$SCRIPT_DIR/daml_docs_json_to_mdx.py" \
  --input-json "$PUBLISH_JSON_PATH" \
  --output-dir "$OUTPUT_DIR" \
  --module-deprecation-first-seen-json "$DEPRECATION_FIRST_SEEN_JSON" \
  --docs-json "$DOCS_JSON" \
  --nav-group-name "Daml Standard Library" \
  --nav-dropdown-name "App Development" \
  --create-nav-group-if-missing \
  --nav-base "$NAV_BASE"

python3 "$SCRIPT_DIR/cleanup_daml_reference_docs_nav.py" \
  --docs-json "$DOCS_JSON" \
  --remove-dropdown-name "Daml Reference Docs" \
  --appdev-dropdown-name "App Development" \
  --remove-legacy-group-name "Generated API Reference"

if [[ "$KEEP_GENERATED_JSON" == true ]]; then
  log "Generated JSON kept under: $TMP_DIR"
fi
