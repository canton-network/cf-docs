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
cd docs-main && mintlify dev
```

The site will be available at http://localhost:3000.

### Useful commands

```bash
# Check for broken links
mintlify broken-links
```

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

### Generate the JSON API reference

This repo includes a checked-in source config plus regenerated local Ledger API OpenAPI snapshots under `config/x2mdx/ledger-api/`.
The generator script refreshes those local `openapi.yaml` snapshots from configured Canton release bundles, rewrites the local manifest, and then regenerates the page and `docs.json` update with the GitHub-pinned `x2mdx`:

```bash
python3 scripts/generate_json_api_reference.py
```

or:

```bash
npm run generate:json-api-reference
```

By default this writes:

- `docs-main/reference/json-api-reference.mdx`
- `docs-main/docs.json`

The generated page is placed directly under the top-level `Reference` dropdown in `docs-main/docs.json`, outside the `MainNet`/`TestNet`/`DevNet` versioned navigation branches.

### Generate the JSON API AsyncAPI reference

This repo also includes a checked-in source config for the Ledger API AsyncAPI bundle inputs under `config/x2mdx/ledger-api-asyncapi/source-artifacts.json`.
The generator script downloads the configured Canton release bundles, extracts `asyncapi.yaml` into `.internal/cache/x2mdx/ledger-api-asyncapi/`, writes a local x2mdx manifest into `.internal/generated/x2mdx/ledger-api-asyncapi/manifest.json`, and then renders the MDX page with the GitHub-pinned `x2mdx`.

Run:

```bash
python3 scripts/generate_json_api_asyncapi_reference.py
```

or:

```bash
npm run generate:json-api-asyncapi-reference
```

By default this writes:

- `docs-main/reference/json-api-asyncapi-reference.mdx`
- `docs-main/docs.json`

The generated page is placed directly under the top-level `Reference` dropdown in `docs-main/docs.json`.

### Generate the Ledger bindings API reference

This repo also includes a checked-in source config for the published Java/Scala bindings Javadoc/Scaladoc jars at `config/x2mdx/ledger-bindings/source-artifacts.json`.
The generator script downloads those jars into `.internal/cache/x2mdx/ledger-bindings/`, writes a local x2mdx manifest into `.internal/generated/x2mdx/ledger-bindings/manifest.json`, and then renders the MDX pages with the GitHub-pinned `x2mdx`.

Run:

```bash
python3 scripts/generate_ledger_bindings_api_reference.py
```

or:

```bash
npm run generate:ledger-bindings-api-reference
```

By default this writes:

- `docs-main/reference/ledger-api-jvm-bindings.mdx`
- `docs-main/reference/java/`
- `docs-main/reference/scala/`
- `docs-main/docs.json`

The generated nav is added under the top-level `Reference` dropdown as `Ledger API JVM Bindings -> Scaladocs/Javadocs`, with each nested group populated directly from the generated JVM package pages.

### Generate the Daml Standard Library reference

This repo also includes a checked-in source config for versioned Daml Standard Library docs JSON generation at `config/x2mdx/daml-standard-library/source-artifacts.json`.
The generator script uses local SDK artifacts via `dpm` or `daml` to build cached docs JSON snapshots under `.internal/cache/x2mdx/daml-standard-library/`, writes a local x2mdx manifest into `.internal/generated/x2mdx/daml-standard-library/manifest.json`, and then renders MDX pages with the GitHub-pinned `x2mdx`.

Run:

```bash
python3 scripts/generate_daml_standard_library_reference.py
```

or:

```bash
npm run generate:daml-standard-library-reference
```

By default this writes:

- `docs-main/appdev/reference/daml-standard-library/`
- `docs-main/docs.json`

The generated nav is added under the top-level `Reference` dropdown as `Daml Standard Library`, with the overview page listed first and the generated module pages grouped under a nested `Modules` foldout.

### Generate the Canton protobuf history reference

This repo also includes a checked-in source config for versioned Canton protobuf descriptor discovery at `config/x2mdx/protobuf-history/source-artifacts.json`.
The generator script clones or fetches a cached bare Canton repo under `.internal/cache/x2mdx/protobuf-history/`, materializes local descriptor images for stable release tags, writes a local x2mdx manifest into `.internal/generated/x2mdx/protobuf-history/manifest.json`, and then renders MDX pages with the GitHub-pinned `x2mdx`.

Run:

```bash
python3 scripts/generate_canton_protobuf_history.py
```

or:

```bash
npm run generate:canton-protobuf-history
```

By default this writes:

- `docs-main/appdev/reference/protobuf-history/`
- `docs-main/docs.json`

The generated nav is added under the top-level `Reference` dropdown as `Canton Protobuf History`, with only the overview page listed in nav. The per-endpoint pages are generated and linked from the overview page but left unlisted.

### Generate the TypeScript bindings reference

This repo also includes a checked-in source config for published `@daml/types` npm artifacts at `config/x2mdx/typescript-bindings/source-artifacts.json`.
The generator script downloads the configured tarballs into `.internal/cache/x2mdx/typescript-bindings/`, installs local package dependencies, renders TypeDoc JSON into `.internal/generated/x2mdx/typescript-bindings/`, writes a local x2mdx manifest, and then rewrites the checked-in Mintlify page with the GitHub-pinned `x2mdx`.

Run:

```bash
python3 scripts/generate_typescript_bindings_reference.py
```

or:

```bash
npm run generate:typescript-bindings-reference
```

By default this writes:

- `docs-main/reference/typescript.mdx`
- `docs-main/docs.json`

The generator also adds that page under the top-level `Reference` dropdown as `Daml TypeScript Bindings -> TypeScript`.

### Generate the Wallet Gateway JSON-RPC reference

This repo also includes a checked-in source config for versioned Wallet Gateway OpenRPC specs from `hyperledger-labs/splice-wallet-kernel` at `config/x2mdx/wallet-gateway-openrpc/source-artifacts.json`.
The generator script clones or fetches a cached bare repo under `.internal/cache/x2mdx/wallet-gateway-openrpc/`, materializes local versioned OpenRPC JSON files, writes a local x2mdx manifest into `.internal/generated/x2mdx/wallet-gateway-openrpc/manifest.json`, and then renders MDX pages with the GitHub-pinned `x2mdx`.

Run:

```bash
python3 scripts/generate_wallet_gateway_openrpc_reference.py
```

or:

```bash
npm run generate:wallet-gateway-openrpc-reference
```

By default this writes:

- `docs-main/reference/wallet-gateway-json-rpc/`
- `docs-main/docs.json`

The generated nav is added under the top-level `Reference` dropdown as `Wallet Gateway JSON-RPC`, with the overview page plus one page per published OpenRPC surface.
