# Daml Prim Sync Plan (digital-asset/docs)

## High-Level Approach

This implementation stays entirely in `digital-asset/docs`:

1. Use `dpm` + `damlc docs --format json` against the installed SDK artifact to generate `daml-prim.json` (no `daml` repo checkout).
2. Convert JSON to MDX using `scripts/daml_docs_json_to_mdx.py`.
3. Update navigation in `docs.json` so generated pages are visible in Mintlify.
4. Run everything through scripts that can be called locally and from CI.
5. Add a GitHub Actions workflow in this repo that runs the scripts in dry-run by default; PR creation is optional.

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

## Remaining Gaps

- GitHub Actions workflow has been added but not executed from this environment yet.
- PR creation path in workflow is implemented but only validated by static review/local logic, not by a live run.
