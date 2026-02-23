# Daml Prim Sync Plan (digital-asset/docs)

## High-Level Approach

This implementation stays entirely in `digital-asset/docs`:

1. Use `dpm` + `damlc docs --format json` against the installed SDK artifact to generate `daml-prim.json` (no `daml` repo checkout).
2. Convert JSON to MDX using `scripts/daml_docs_json_to_mdx.py`.
3. Sync the latest 3 stable SDK versions (or explicit versions) into `docs-main/daml-reference/daml-prim-api/vX-Y-Z`.
4. Update navigation in `docs.json` with `Daml Reference Docs` -> `Daml Prim API` version groups.
5. Remove legacy `Generated API Reference` groups from `App Development`.
6. Run everything through scripts that can be called locally and from CI.
7. Add a GitHub Actions workflow in this repo that runs the scripts in dry-run by default; PR creation is optional.

## Checklist

- [x] 1. Confirm `dpm damlc docs --format json` can generate `daml-prim.json` from installed SDK sources.
- [x] 2. Add `dpm` to the repo nix shell in a reproducible way.
- [x] 3. Add a script to generate `daml-prim.json` from `dpm` (configurable SDK/LF target).
- [x] 4. Add a script to run JSON -> MDX conversion using the shared converter.
- [x] 5. Make navigation update safe and deterministic for this docs repo layout.
- [x] 6. Document local usage for generation + conversion + dry-run.
- [x] 7. Add GitHub Actions workflow in `digital-asset/docs`.
- [x] 8. Wire workflow to run scripts via nix shell.
- [x] 9. Make workflow dry-run by default and support optional PR creation as draft.
- [x] 10. Run local end-to-end dry-run test and capture exact command for you.
- [x] 11. Run unit tests for converter and verify no regressions.
- [x] 12. Update this checklist with final status and remaining gaps.
- [x] 13. Align docs/workflow wording with latest-3 multi-version sync.
- [x] 14. Validate navigation updater against real `docs.json` schema (`navigation.dropdowns`).

## Remaining Gaps

- Workflow dispatch cannot be triggered by API until this workflow exists on default branch `main`.
- PR creation path in workflow (`dry_run=false`) has not been run yet due current dry-run validation mode.

## Validation Notes

- Pull request dry-run workflow validated successfully on branch `daml-json-to-mdx-converter-clean`.
- Latest successful run: https://github.com/digital-asset/docs/actions/runs/22293484830
- Local integration dry-run validated:
  - `scripts/sync_daml_prim_api_from_dpm.sh --input-json scripts/tests/fixtures/sample_prim.json --sdk-version 3.4.10 --docs-json /tmp/docs-json.* --output-dir /tmp/daml-ref-out --skip-install`
  - Verified legacy `Generated API Reference` groups were removed and `Daml Reference Docs` + `Daml Prim API` were created.
- The workflow now sets:
  - `NIX_PATH` for `nix-shell` compatibility in GitHub Actions.
  - `SKIP_NPM_INSTALL=1` to avoid unnecessary npm install in CI shell startup.
  - `PYTHONDONTWRITEBYTECODE=1` to avoid `__pycache__` diffs in CI.
