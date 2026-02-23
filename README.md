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
