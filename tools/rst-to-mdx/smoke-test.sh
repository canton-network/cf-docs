#!/usr/bin/env bash
# =============================================================================
# smoke-test.sh — End-to-end smoke test for rst-to-mdx.
#
# Runs the built binary against a known RST fixture from
# docs-website/ and compares the output to a reference MDX.
# Exits non-zero on any mismatch that is NOT expected for the current phase.
#
# Usage:
#   ./smoke-test.sh             # run all smoke cases
#   ./smoke-test.sh --keep      # keep the temp output for inspection
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()    { echo -e "${YELLOW}[INFO]${NC}    $1"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $1"; }
log_error()   { echo -e "${RED}[FAIL]${NC}    $1" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BIN="$SCRIPT_DIR/rst-to-mdx"

KEEP=false
[[ "${1:-}" == "--keep" ]] && KEEP=true

if [[ ! -x "$BIN" ]]; then
    log_info "Binary not found at $BIN — building…"
    (cd "$SCRIPT_DIR" && go build -o rst-to-mdx ./cmd/rst-to-mdx)
fi

# ---------------------------------------------------------------------------
# Case 1: --version smoke
# ---------------------------------------------------------------------------
log_info "case 1: --version prints without error"
VERSION_OUT="$("$BIN" --version 2>&1)"
if [[ "$VERSION_OUT" != rst-to-mdx* ]]; then
    log_error "expected 'rst-to-mdx <version>', got: $VERSION_OUT"
    exit 1
fi
log_success "version: $VERSION_OUT"

# ---------------------------------------------------------------------------
# Case 2: convert a known RST fixture and check basic MDX invariants
# ---------------------------------------------------------------------------
RST="$REPO_ROOT/docs-website/docs/replicated/quickstart/3.5/sdk/quickstart/download/cnqs-installation.rst"
REFERENCE_MDX="$REPO_ROOT/docs/docs-main/appdev/quickstart/prerequisites.mdx"

if [[ ! -f "$RST" ]]; then
    log_error "fixture RST missing: $RST"
    exit 1
fi
log_info "case 2: converting $RST"

TMPDIR="$(mktemp -d)"
trap '[[ "$KEEP" == true ]] && echo "kept: $TMPDIR" || rm -rf "$TMPDIR"' EXIT

OUT="$TMPDIR/out.mdx"
"$BIN" "$RST" "$OUT" --verbose

# Basic invariants for a Phase-0 conversion:
#   - file exists and is non-empty
#   - starts with YAML frontmatter
#   - contains the COPIED_START provenance marker
#   - contains the COPIED_END closer
#   - closes newline-terminated

[[ -s "$OUT" ]]                          || { log_error "output empty"; exit 1; }
head -n 1 "$OUT" | grep -q "^---$"        || { log_error "missing opening '---' frontmatter fence"; exit 1; }
grep -q "COPIED_START"                 "$OUT" || { log_error "missing COPIED_START marker"; exit 1; }
grep -q "COPIED_END"                   "$OUT" || { log_error "missing COPIED_END marker"; exit 1; }
tail -c 1 "$OUT" | grep -q "^$"          || { log_error "missing trailing newline"; exit 1; }

log_success "Phase-0 invariants pass"

# ---------------------------------------------------------------------------
# Case 3: diff summary against the reference migrated MDX
#
# This is informational only while the converter is in Phase 0 — the diff
# WILL be large because transforms aren't wired yet. The point is to surface
# the gap so we can watch it shrink across phases.
# ---------------------------------------------------------------------------
if [[ -f "$REFERENCE_MDX" ]]; then
    ADDED=$(diff -u "$REFERENCE_MDX" "$OUT" | grep -c '^+[^+]' || true)
    REMOVED=$(diff -u "$REFERENCE_MDX" "$OUT" | grep -c '^-[^-]' || true)
    log_info "diff vs. reference ($(basename "$REFERENCE_MDX")): +$ADDED / -$REMOVED lines"
    log_info "(expected to be large in Phase 0 — tracking metric)"
fi

# ---------------------------------------------------------------------------
# Case 4: --dry-run does not create a file
# ---------------------------------------------------------------------------
DRY_OUT="$TMPDIR/dry-run.mdx"
log_info "case 4: --dry-run leaves disk untouched"
"$BIN" "$RST" "$DRY_OUT" --dry-run > /dev/null
if [[ -e "$DRY_OUT" ]]; then
    log_error "--dry-run wrote a file"
    exit 1
fi
log_success "--dry-run passes"

# ---------------------------------------------------------------------------
# Case 5: empty input is rejected
# ---------------------------------------------------------------------------
log_info "case 5: empty input rejected"
EMPTY="$TMPDIR/empty.rst"
: > "$EMPTY"
if "$BIN" "$EMPTY" "$TMPDIR/empty.mdx" 2>/dev/null; then
    log_error "empty input should fail"
    exit 1
fi
log_success "empty input rejected as expected"

echo
log_success "smoke test passed (Phase 0)"
