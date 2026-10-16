# Contribution reports

Tools that report on pull requests, issues and reviews in this repository. They are not
part of the documentation site, and their output is private: generated files are ignored
by git (see `.gitignore`) and published only to Google Drive.

## Contribution tracker (Google Sheet)

`update_tracker.sh --upload` keeps the tracker Google Sheet current; a scheduled task runs it
every morning. It downloads the Sheet, adds activity updated since its last refresh, keeps the
affiliations people edited on the Contributors tab, and uploads it in place (same file, same link).
It checks the result on Google's side and restores the previous version if the check fails.

- `build_tracker.py`: fetches GitHub data and builds the workbook: data tabs plus the
  Contributors tab, whose affiliations people edit in the Sheet.
- `tracker_reports.py`: the report tabs. Overview is fixed and the same for everyone; Activity,
  People and Open work are driven by shared dropdowns.
- `tracker_env.sh`: runs a command with Python, openpyxl and LibreOffice from nixpkgs.

Needs `gh` (signed in), `rclone` with a Google Drive remote named `gdrive docs reports`,
`nix`, and `swift` (macOS) for rendering pages to check.

## Weekly PDF report

`publish_weekly.sh [--end YYYY-MM-DD] [--upload]` builds a one-page HTML/PDF report for the
week ending at Monday noon US Eastern (`generate_weekly.py`), renders its pages for a layout
check (`render_pdf_pages.swift`), and with `--upload` adds it to a dated Drive folder.

## Affiliations

`contributors.json` maps GitHub logins to Digital Asset, Canton Foundation or bots. Logins
that are not listed count as Digital Asset when they carry a `-da` / `DA` marker, and as
external otherwise.
