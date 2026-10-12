#!/usr/bin/env bash
# Adds the latest GitHub activity to the cf-docs contribution tracker Google Sheet.
#
#   1. downloads the current Sheet as .xlsx (keeps its data and Contributors edits)
#   2. merges in pull requests, issues and reviews updated since its last refresh
#   3. checks the data tabs' formulas with LibreOffice and stops on any error
#   4. with --upload, replaces the Sheet's contents in place (same file, same link), checks
#      Google's results on the report tabs (restoring the previous version if they are wrong),
#      and renders the report tabs to PNGs for a visual check
#
# Usage: reports/update_tracker.sh [--upload]
set -euo pipefail

cd "$(dirname "$0")/.."

sheet_id="1jK9nWivUBkwVjTgLJYdTrqBVOmqJT97-BToA724e83Q"
remote="gdrive docs reports"
work="reports/tracker/work"
xlsx="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
upload=false
[ "${1:-}" = "--upload" ] && upload=true

rm -rf "$work" && mkdir -p "$work"

# rclone refreshes the Google sign-in when it touches the remote; reuse that token for the
# Drive API, which rclone cannot use to update a Google Sheet in place.
token() {
  timeout 120 rclone lsf "$remote:Reports" --max-depth 1 >/dev/null 2>&1 || true
  rclone config dump | python3 -c "import json,sys; print(json.loads(json.load(sys.stdin)['$remote']['token'])['access_token'])"
}

# Drive rate-limits rclone's shared Google project, so retry with backoff.
drive() {  # drive <curl args...>; the response body goes wherever the args say
  for attempt in 1 2 3 4 5 6 7 8; do
    code=$(curl -s -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$@")
    [ "$code" = 200 ] && return 0
    sleep $((attempt * 8))
  done
  echo "Drive request failed with HTTP $code" >&2
  return 1
}

TOKEN="$(token)"
drive -o "$work/current.xlsx" "https://www.googleapis.com/drive/v3/files/$sheet_id/export?mimeType=$xlsx"

reports/tracker_env.sh "python3 reports/build_tracker.py --from $work/current.xlsx --out $work/new.xlsx \
  && soffice --headless -env:UserInstallation=file://$PWD/$work/lo-profile --convert-to xlsx --outdir $work/calc $work/new.xlsx >/dev/null 2>&1 \
  && python3 - <<'PY'
# The report tabs use Google Sheets functions LibreOffice cannot evaluate; they are checked
# after upload. Here, only the data tabs.
from openpyxl import load_workbook
wb = load_workbook('$work/calc/new.xlsx', data_only=True)
codes = {'#REF', '#VALUE', '#NAME', '#DIV', '#N/A', '#NUM', '#NULL', '#ERROR'}
errors = [f'{t}!{c.coordinate}={c.value}' for t in ('PRs', 'Reviews', 'Issues', 'Contributors')
          for row in wb[t].iter_rows() for c in row
          if isinstance(c.value, str) and c.value.rstrip('!?/0').upper() in codes]
if errors:
    raise SystemExit('formula errors in data tabs: ' + ', '.join(errors[:20]))
print('data tabs: no formula errors')
PY"

upload() {  # upload <xlsx>: replace the Sheet's contents in place
  TOKEN="$(token)"
  drive -o "$work/upload.json" -X PATCH -H "Content-Type: $xlsx" --data-binary "@$1" \
    "https://www.googleapis.com/upload/drive/v3/files/$sheet_id?uploadType=media&fields=id,mimeType,modifiedTime"
  python3 -c "
import json; r = json.load(open('$work/upload.json'))
assert r['id'] == '$sheet_id' and r['mimeType'] == 'application/vnd.google-apps.spreadsheet', r
print('uploaded $1:', r['modifiedTime'])"
}

if $upload; then
  upload "$work/new.xlsx"
  # Check Google's own results: no error values on the report tabs, and the default
  # Activity view (last week, everyone) equal to the independently computed figures.
  drive -o "$work/after.xlsx" "https://www.googleapis.com/drive/v3/files/$sheet_id/export?mimeType=$xlsx"
  if ! reports/tracker_env.sh "python3 - <<'PY'
import json
from openpyxl import load_workbook
wb = load_workbook('$work/after.xlsx', data_only=True)
codes = {'#REF', '#VALUE', '#NAME', '#DIV', '#N/A', '#NUM', '#NULL', '#ERROR'}
problems = [f'{t}!{c.coordinate}={c.value}' for t in ('Activity', 'People', 'Open work')
            for row in wb[t].iter_rows() for c in row
            if isinstance(c.value, str) and c.value.rstrip('!?/0').upper() in codes]
expected = json.load(open('$work/new.expected.json'))
a = wb['Activity']
got = {'PRs opened': a['A8'].value, 'PRs merged': a['C8'].value, 'PRs closed without merging': a['E8'].value,
       'PRs reviewed (reviewer–PR pairs)': a['A12'].value, 'Issues opened': a['C12'].value,
       'Issues closed': a['E12'].value}
for k, v in got.items():
    if v != expected[k]:
        problems.append(f'Activity {k}: sheet {v}, expected {expected[k]}')
print('activity (last week):', a['A2'].value, '|', ', '.join(f'{k} {v}' for k, v in got.items()))
if problems:
    raise SystemExit('check failed: ' + '; '.join(problems[:20]))
print('report tabs: no errors; default view matches')
PY"; then
    if [ -s reports/tracker/last-good.xlsx ]; then
      echo "restoring the previous version" >&2
      upload reports/tracker/last-good.xlsx
    fi
    exit 1
  fi
  cp "$work/new.xlsx" reports/tracker/last-good.xlsx
  # Google's rendering of the report tabs: the first pages of the PDF export.
  drive -o "$work/sheet.pdf" "https://www.googleapis.com/drive/v3/files/$sheet_id/export?mimeType=application/pdf"
  swift reports/render_pdf_pages.swift "$work/sheet.pdf" "$work/page" 8 >/dev/null
  echo "report pages: $(ls $work/page-*.png | sort -V | tr '\n' ' ')"
fi
