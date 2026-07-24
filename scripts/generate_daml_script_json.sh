#!/usr/bin/env bash
# Copyright (c) 2026 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: generate_daml_script_json.sh --output-json PATH [options]

Generate Daml Script docs JSON from installed daml-script DAR artifacts.

SDK source selection:
- dpm (default): use DPM cache + cached damlc binary.
- auto: prefer DPM cache under ~/.dpm, fallback to DAML SDK installation
  under ~/.daml/sdk/<version>.
- daml: use DAML SDK layout + damlc binary.

Options:
  --output-json PATH   Destination JSON file path. (required)
  --sdk-version VER    SDK version to use. Default: latest stable from get.digitalasset.com.
  --lf-target VER      LF target folder (e.g. 2.2). Default: highest numeric target available.
  --sdk-source SRC     One of: auto, daml, dpm. Default: dpm.
  --daml-home PATH     DAML home dir. Default: $DAML_HOME or ~/.daml
  --dpm-home PATH      DPM home dir. Default: $DPM_HOME or ~/.dpm
  --skip-install       Skip installing missing SDK for selected source.
  -h, --help           Show this help.

Environment:
  DAML_DOCS_SDK_VERSION  Default for --sdk-version.
  DAML_DOCS_LF_TARGET    Default for --lf-target.
  DAML_DOCS_SDK_SOURCE   Default for --sdk-source.
  DAML_HOME              Default for --daml-home.
  DPM_HOME               Default for --dpm-home.

Example:
  ./scripts/generate_daml_script_json.sh \
    --output-json /tmp/daml-script.json \
    --sdk-version 3.5.1 \
    --lf-target 2.2 \
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
if [[ "$DAML_DOCS_SDK_SOURCE" != "auto" && "$DAML_DOCS_SDK_SOURCE" != "daml" && "$DAML_DOCS_SDK_SOURCE" != "dpm" ]]; then
  echo "Invalid --sdk-source '$DAML_DOCS_SDK_SOURCE'. Expected one of: auto, daml, dpm." >&2
  exit 1
fi

daml_docs_sdk_configure

dpm_daml_script_component_root() {
  printf '%s\n' "$DAML_DOCS_DPM_HOME/cache/components/daml-script/$DAML_DOCS_SDK_VERSION"
}

daml_daml_script_component_root() {
  printf '%s\n' "$DAML_DOCS_DAML_HOME/sdk/$DAML_DOCS_SDK_VERSION/daml-script"
}

resolve_daml_script_dar() {
  local component_roots=()
  local candidate
  local candidates=()

  if [[ "$DAML_DOCS_SDK_SOURCE" == "dpm" ]]; then
    component_roots+=("$(dpm_daml_script_component_root)")
  elif [[ "$DAML_DOCS_SDK_SOURCE" == "daml" ]]; then
    component_roots+=("$(daml_daml_script_component_root)")
  fi

  for component_root in "${component_roots[@]}"; do
    if [[ ! -d "$component_root" ]]; then
      continue
    fi
    candidate="$component_root/daml-script-$DAML_DOCS_LF_TARGET.dar"
    if [[ -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
    mapfile -t candidates < <(find "$component_root" -maxdepth 1 -type f -name 'daml-script-*.dar' | sort)
    for candidate in "${candidates[@]}"; do
      if [[ "$(basename -- "$candidate")" == "daml-script-$DAML_DOCS_LF_TARGET.dar" ]]; then
        echo "$candidate"
        return 0
      fi
    done
    if [[ "${#candidates[@]}" -eq 1 ]]; then
      echo "${candidates[0]}"
      return 0
    fi
  done

  echo "No daml-script DAR found for SDK ${DAML_DOCS_SDK_VERSION} and LF target ${DAML_DOCS_LF_TARGET}." >&2
  echo "Checked component roots:" >&2
  for component_root in "${component_roots[@]}"; do
    printf '  %s\n' "$component_root" >&2
  done
  echo "Install the SDK with dpm install ${DAML_DOCS_SDK_VERSION} (or daml install) and retry." >&2
  return 1
}

generate_daml_script_json() {
  local output_json="$1"
  local dar_path
  local extract_dir
  local script_file
  local internal_file

  dar_path="$(resolve_daml_script_dar)"
  extract_dir="$(mktemp -d "${TMPDIR:-/tmp}/daml-script-src.XXXXXX")"
  trap 'rm -rf "$extract_dir"' RETURN

  if ! unzip -q "$dar_path" '*.daml' -d "$extract_dir"; then
    echo "Failed to extract .daml files from $dar_path" >&2
    return 1
  fi

  script_file="$(find "$extract_dir" -path '*/Daml/Script.daml' | sort | head -1)"
  internal_file="$(find "$extract_dir" -path '*/Daml/Script/Internal.daml' | sort | head -1)"
  if [[ -z "$script_file" || -z "$internal_file" ]]; then
    echo "Failed to locate Daml.Script entrypoint files in $dar_path" >&2
    return 1
  fi

  daml_docs_log "Generating daml-script JSON"
  daml_docs_log "source=$DAML_DOCS_SDK_SOURCE sdk=$DAML_DOCS_SDK_VERSION lf_target=$DAML_DOCS_LF_TARGET package=daml-script dar=$dar_path entrypoints=2"
  "${DAML_DOCS_DOCS_CMD[@]}" \
    --output "$output_json" \
    --package-name daml-script \
    --format json \
    --target "$DAML_DOCS_LF_TARGET" \
    --package-db "$DAML_DOCS_PKG_DB_ROOT" \
    -Wno-deprecated-exceptions \
    "$script_file" \
    "$internal_file"

  python3 - "$output_json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
modules = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(modules, list):
    raise SystemExit(f"Expected list JSON payload in {path}")

keep = ("Daml.Script", "Daml.Script.Internal")
by_name = {
    str(module.get("md_name", "")): module
    for module in modules
    if isinstance(module, dict) and isinstance(module.get("md_name"), str)
}
filtered = [by_name[name] for name in keep if name in by_name]
missing = [name for name in keep if name not in by_name]
if missing:
    raise SystemExit(f"Missing expected daml-script modules in {path}: {', '.join(missing)}")

path.write_text(json.dumps(filtered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Filtered daml-script modules: {', '.join(keep)}")
PY
}

mkdir -p "$(dirname -- "$OUTPUT_JSON")"
generate_daml_script_json "$OUTPUT_JSON"
daml_docs_log "Wrote $OUTPUT_JSON"
