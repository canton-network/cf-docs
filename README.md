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

### Run all generated reference docs

Load the repo's `direnv` / `nix` shell first, then rerun all generated reference-doc wrappers in one command:

```bash
direnv allow
python3 scripts/generate_all_reference_docs.py
```

Use `--dry-run` to print the exact per-step commands without executing them.

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

The generated page is placed directly under the top-level `API Reference` dropdown in `docs-main/docs.json`, outside the `MainNet`/`TestNet`/`DevNet` versioned navigation branches.

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

The generated page is placed directly under the top-level `API Reference` dropdown in `docs-main/docs.json`.

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

The generated nav is added under the top-level `API Reference` dropdown as `Ledger API JVM Bindings -> Scaladocs/Javadocs`, with each nested group populated directly from the generated JVM package pages.

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

The generated nav is added under the top-level `API Reference` dropdown as `Daml Standard Library`, with the overview page listed first and the generated module pages grouped under a nested `Modules` foldout.

### Generate the Canton protobuf history reference

This repo also includes a checked-in source config for Canton release-bundle protobuf inputs at `config/x2mdx/protobuf-history/source-artifacts.json`.
The generator script discovers stable Canton versions from the source repo tags, downloads the matching `canton-open-source-<version>.tar.gz` bundles from `canton.io/releases`, extracts the published `protobuf/` tree under `.internal/cache/x2mdx/protobuf-history/`, compiles local descriptor images with `grpc_tools.protoc`, writes a local x2mdx manifest into `.internal/generated/x2mdx/protobuf-history/manifest.json`, and then renders MDX pages with the GitHub-pinned `x2mdx`.

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

The generated nav is added under the top-level `API Reference` dropdown as `Canton Protobuf History`, with only the overview page listed in nav. The per-endpoint pages are generated and linked from the overview page but left unlisted.

### Generate the gRPC Ledger API reference

This repo also includes a checked-in source config for the Ledger API gRPC protobuf surface at `config/x2mdx/grpc-ledger-api-reference/source-artifacts.json`.
The generator script reuses the published Canton release-bundle protobuf acquisition flow, filters the resulting protobuf report to `com.daml.ledger.api.v2*`, and writes a dedicated Ledger API-only MDX surface without modifying `x2mdx`.

Run:

```bash
python3 scripts/generate_grpc_ledger_api_reference.py
```

or:

```bash
npm run generate:grpc-ledger-api-reference
```

By default this writes:

- `docs-main/reference/grpc-ledger-api-reference/`
- `docs-main/docs.json`

The generated nav is added under the top-level `Reference` dropdown as `gRPC Ledger API Reference`, with the overview page first and the generated package pages grouped under a nested `Packages` foldout.

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

The generator also adds that page under the top-level `API Reference` dropdown as `Daml TypeScript Bindings -> TypeScript`.

### Generate the Wallet Gateway JSON-RPC reference

This repo also includes a checked-in source config for versioned Wallet Gateway OpenRPC specs from `hyperledger-labs/splice-wallet-kernel` at `config/x2mdx/wallet-gateway-openrpc/source-artifacts.json`.
The generator script discovers versions from GitHub releases filtered to the `@canton-network/wallet-gateway-remote@` release stream, clones or fetches a cached bare repo under `.internal/cache/x2mdx/wallet-gateway-openrpc/`, materializes local versioned OpenRPC JSON files from the matching tag snapshots, writes a local x2mdx manifest into `.internal/generated/x2mdx/wallet-gateway-openrpc/manifest.json`, and then renders MDX pages with the GitHub-pinned `x2mdx`.

Run:

```bash
python3 scripts/generate_wallet_gateway_openrpc_reference.py
```

or:

```bash
npm run generate:wallet-gateway-openrpc-reference
```

### Generate the Splice Scan OpenAPI reference

This repo also includes a checked-in source config for the published decentralized-canton-sync OpenAPI bundle at `config/x2mdx/splice-scan-openapi/source-artifacts.json`.
The generator script discovers matching stable releases through the GitHub releases API, downloads `*_openapi.tar.gz` bundle assets into `.internal/cache/x2mdx/splice-openapi/`, materializes all bundled YAML files into local versioned fixtures for `$ref` resolution, writes a local x2mdx manifest into `.internal/generated/x2mdx/splice-scan-openapi/manifest.json`, and then renders the checked-in Mintlify pages with the GitHub-pinned `x2mdx`.

Run:

```bash
python3 scripts/generate_splice_scan_openapi_reference.py
```

or:

```bash
npm run generate:splice-scan-openapi-reference
```

By default this writes:

- `docs-main/reference/splice-scan-openapi/`
- `docs-main/docs.json`

The generated nav is added under the top-level `API Reference` dropdown as `Splice APIs -> Scan APIs`, with the overview page listed first followed by the generated Scan spec pages.

### Generate the Splice Validator OpenAPI reference

This repo also includes a checked-in source config for the published decentralized-canton-sync validator-family OpenAPI bundle surface at `config/x2mdx/splice-validator-openapi/source-artifacts.json`.
The generator script reuses the docs-side Splice OpenAPI release-bundle helper, materializes the validator-family YAML fixtures from `*_openapi.tar.gz`, writes a local x2mdx manifest into `.internal/generated/x2mdx/splice-validator-openapi/manifest.json`, and then renders the checked-in Mintlify pages with the GitHub-pinned `x2mdx`.

Run:

```bash
python3 scripts/generate_splice_validator_openapi_reference.py
```

or:

```bash
npm run generate:splice-validator-openapi-reference
```

By default this writes:

- `docs-main/reference/splice-validator-openapi/`
- `docs-main/docs.json`

The generated nav is added under the top-level `API Reference` dropdown as `Splice APIs -> Validator APIs`, with the overview page listed first followed by the generated validator-family spec pages.

### Generate the Splice token-standard OpenAPI reference

This repo also includes a checked-in source config for the published decentralized-canton-sync token-standard OpenAPI bundle surface at `config/x2mdx/splice-token-standard-openapi/source-artifacts.json`.
The generator script reuses the docs-side Splice OpenAPI release-bundle helper, materializes the token-standard YAML fixtures from `*_openapi.tar.gz`, writes a local x2mdx manifest into `.internal/generated/x2mdx/splice-token-standard-openapi/manifest.json`, and then renders the checked-in Mintlify pages with the GitHub-pinned `x2mdx`.

Run:

```bash
python3 scripts/generate_splice_token_standard_openapi_reference.py
```

or:

```bash
npm run generate:splice-token-standard-openapi-reference
```

By default this writes:

- `docs-main/reference/splice-token-standard-openapi/`
- `docs-main/docs.json`

The generated nav is added under the top-level `API Reference` dropdown as `Splice APIs -> Token Standard APIs`, with the overview page listed first followed by the generated token-standard spec pages.

### Generate the Splice Daml API reference

This repo also includes a checked-in source config for the published decentralized-canton-sync Splice Daml API surface at `config/x2mdx/splice-daml-api/source-artifacts.json`.
The generator script discovers matching stable releases through the GitHub releases API, downloads the `*_splice-node.tar.gz` bundle assets into `.internal/cache/x2mdx/splice-daml-api/`, validates that the configured family list still matches the live `docs.sync.global/app_dev/api/` surface embedded in the published bundle docs, extracts the corresponding DARs, runs `daml damlc docs --format json` on the extracted `.daml` sources, writes per-family x2mdx manifests into `.internal/generated/x2mdx/splice-daml-api/`, and then renders the checked-in Mintlify pages with the GitHub-pinned `x2mdx`.

Run:

```bash
python3 scripts/generate_splice_daml_api_reference.py
```

or:

```bash
npm run generate:splice-daml-api-reference
```

By default this writes:

- `docs-main/reference/splice-daml-api/`
- `docs-main/docs.json`

The generated nav is added under the top-level `API Reference` dropdown as `Splice APIs -> Daml APIs`. The overview page records the one currently-blocked live family, `splice-token-standard-test`, whose live docs exist but whose release bundle does not currently ship a matching DAR.

By default this writes:

- `docs-main/reference/wallet-gateway-json-rpc/`
- `docs-main/docs.json`

The generated nav is added under the top-level `API Reference` dropdown as `Wallet Gateway JSON-RPC`, with the overview page plus one page per published OpenRPC surface.
