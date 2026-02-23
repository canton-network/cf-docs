Copyright (c) 2025 Digital Asset (Switzerland) GmbH and/or its affiliates. All rights reserved.
SPDX-License-Identifier: Apache-2.0 AND CC-BY-4.0

docs
====

This repo manages the contents of the docs.canton.network website.

## Local Development

### Prerequisites

- Node.js 20.17 or higher (LTS recommended)

### Running the dev server

```bash
# Install Mintlify CLI (first time only)
npm i -g mintlify

# Start local dev server
mintlify dev
```

The site will be available at http://localhost:3000.

### Useful commands

```bash
# Check for broken links
mintlify broken-links
```

## Daml API generation

This repo includes automation to generate and sync Daml Prim API docs from published `dpm` artifacts:
- `scripts/generate_daml_prim_json_from_dpm.sh`
- `scripts/sync_daml_prim_api_from_dpm.sh`
- `scripts/daml_docs_json_to_mdx.py`

### Reviewer guide for this branch

#### Why this exists

We are centralizing generated-docs production in `digital-asset/docs` and enforcing a clear separation of concerns:
- producer repos are responsible for publishing artifacts
- the `docs` repo is responsible for turning those artifacts into generated docs pages and navigation

For Daml Prim API specifically, this means `docs` consumes published SDK artifacts via `dpm` and performs generation/conversion in this repo, rather than coupling docs generation to source checkout/build logic in other repos.

#### Scope in this branch

- generate `damlc docs --format json` output from installed SDK artifacts
- convert that JSON to MDX pages
- version generated output under `docs-main/daml-reference/daml-prim-api/vX-Y-Z`
- update `docs.json` navigation to:
  - create/update `Daml Reference Docs`
  - create `Daml Prim API` groups per version
  - remove legacy `Generated API Reference` groups from `App Development`
- support scheduled/manual sync through GitHub Actions

#### Key behavior

- default sync target is latest 3 stable SDK versions from `dpm version --all -o json`
- explicit versions can be provided via `--versions`
- `--input-json` is supported in single-version mode for local testing
- shell scripts orchestrate; helper Python scripts handle parsing/transforms

#### Main files to review

- `scripts/generate_daml_prim_json_from_dpm.sh`
- `scripts/sync_daml_prim_api_from_dpm.sh`
- `scripts/daml_docs_json_to_mdx.py`
- `scripts/select_latest_lf_target.py`
- `scripts/list_latest_stable_dpm_versions.py`
- `scripts/relative_posix_path.py`
- `scripts/append_version_nav_entry.py`
- `scripts/update_daml_reference_docs_from_entries.py`
- `.github/workflows/sync-daml-prim-api.yml`
- `scripts/tests/test_daml_docs_json_to_mdx.py`

Quick local dry-run:

```bash
./scripts/sync_daml_prim_api_from_dpm.sh
```

This syncs the latest 3 stable SDK versions by default and updates the
`Daml Reference Docs` navigation section.

Usage details and test commands are documented in `scripts/README.md`.

### Troubleshooting

**Node version error**: If you see "mint dev is not supported on node versions below 20.17", upgrade Node.js:

```bash
# Using nvm
nvm install 20
nvm use 20
```

## License

This repository uses a dual-license model:

- **Documentation prose** (`.mdx` files, text content): [Creative Commons Attribution 4.0 International (CC-BY-4.0)](https://creativecommons.org/licenses/by/4.0/) — see [LICENSE-DOCS](LICENSE-DOCS)
- **Code snippets and configuration** (embedded code examples, scripts, JSON config): [Apache License 2.0](http://www.apache.org/licenses/LICENSE-2.0) — see [LICENSE](LICENSE)

### Direnv + Nix workflow

This repo includes `.envrc` and `shell.nix` for a reproducible local toolchain.

Required:
- `direnv`
- `nix`

Then run:

```bash
direnv allow
mintlify dev
```
