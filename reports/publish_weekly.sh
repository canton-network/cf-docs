#!/usr/bin/env bash
# Builds the weekly cf-docs report as HTML and PDF, renders the PDF pages to PNG for a
# layout check, and with --upload adds it to the dated Drive folder.
#
# Usage: reports/publish_weekly.sh [--end 2026-10-05] [--upload]
set -euo pipefail

cd "$(dirname "$0")/.."

remote="gdrive docs reports"
chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
end_args=()
upload=false
while [ $# -gt 0 ]; do
  case "$1" in
    --end) end_args=(--end "$2"); shift 2 ;;
    --upload) upload=true; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

git fetch origin main --quiet

html="$(python3 reports/generate_weekly.py ${end_args[@]+"${end_args[@]}"})"
dir="$(dirname "$html")"
label="$(basename "$dir")"
start_label="$(date -j -v-7d -f %Y-%m-%d "$label" +%Y-%m-%d)"
name="cf-docs-weekly-$start_label-to-$label.pdf"
pdf="$dir/$name"

timeout 120 "$chrome" --headless --no-pdf-header-footer --virtual-time-budget=10000 \
  --print-to-pdf="$pdf" "file://$html" 2>/dev/null
[ -s "$pdf" ] || { echo "Chrome did not produce $pdf" >&2; exit 1; }

rm -f "$dir"/page-*.png
pages="$(timeout 180 swift reports/render_pdf_pages.swift "$pdf" "$dir/page")"
echo "html:  $html"
echo "pdf:   $pdf ($pages pages)"
echo "pages: $dir/page-1.png … page-$pages.png"

if $upload; then
  # Drive rate-limits rclone's shared client, so allow generous retries.
  # One file per week, named by its date range; earlier weeks are never touched.
  timeout 600 rclone copyto "$pdf" "$remote:Reports/cf-docs-weekly/$name" --retries 5 -v 2>&1 | grep -E "Copied|ERROR"
fi
