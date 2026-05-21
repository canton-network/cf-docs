Copyright (c) 2026 Canton Network. All rights reserved.
SPDX-License-Identifier: Apache-2.0 AND CC-BY-4.0

docs
====

This repo manages the contents of the docs.canton.network website.

## Local Development

### Prerequisites

- Node.js 20.17 or higher (LTS recommended)

### Running the dev server

```bash
direnv allow
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
The Nix package set is pinned by `nix/nixpkgs.src.json`.

Required:
- `direnv`
- `nix`

Then run:

```bash
direnv allow
cd docs-main && mintlify dev
```

### Run all generated reference docs

Load the repo's `direnv` / `nix` shell first, then rerun all generated reference-doc wrappers in one command. The wrappers also re-exec through the docs repo shell themselves, so they do not pick up a local `x2mdx` checkout from ambient `PATH`:

```bash
direnv allow
python3 scripts/generate_all_reference_docs.py
```

Use `--dry-run` to print the exact per-step commands without executing them.

### Generate the Version Compatibility Dashboard

The version dashboard generator collects the public sources that are safe to automate, preserves the fields that still need a manual or owner-approved source, rewrites the dashboard config, and regenerates the published MDX snippet consumed by the version dashboard page.

Run:

```bash
python3 scripts/generate_network_component_versions.py
```

or:

```bash
npm run generate:version-compatibility-dashboard
```

By default this writes:

- `config/repo-version-config.json`
- `docs-main/snippets/generated/version-dashboard-data.mdx`

Use `--dry-run` to inspect the generated config without writing files.

Source rules:

| Dashboard entry | Sourcing rule |
| --- | --- |
| `Splice` | Read from the network `/info` endpoint: MainNet `https://docs.global.canton.network.sync.global/info`, TestNet `https://docs.test.global.canton.network.sync.global/info`, DevNet `https://docs.dev.global.canton.network.sync.global/info`. Cross-check against the same network's `/index.html` Docker image tag and Helm chart version. |
| `Canton` | Read the network Splice version from `/info`, derive the matching `canton-network/splice` release-line branch, then read `version` from `nix/canton-sources.json`: MainNet `https://github.com/canton-network/splice/blob/release-line-0.6.2/nix/canton-sources.json`, TestNet `https://github.com/canton-network/splice/blob/release-line-0.6.3/nix/canton-sources.json`, DevNet `https://github.com/canton-network/splice/blob/release-line-0.6.4/nix/canton-sources.json`. Use release-line branches instead of tags because branch updates require review while tags can be moved. The config key is still `damlSdk` for compatibility with the existing dashboard component. |
| `Daml SDK installer` | Do not use legacy `https://get.daml.com/`; that is the old 2.x Daml assistant path. For Daml 3 / DPM, install DPM with `curl https://get.digitalasset.com/install/install.sh | sh`, then use `dpm install latest`. The latest stable SDK version is exposed at `https://get.digitalasset.com/install/latest`. |
| `PQS` | Keep as manual/fallback for now. A generator can infer a recommendation from PQS docs compatibility tables, but recent updates were Slack-sourced, so this needs owner confirmation before being treated as authoritative. |
| `Token Standard` | Read from the npm `latest` dist-tag for `@canton-network/core-token-standard`. |
| `Wallet SDK` | Read from the npm `latest` dist-tag for `@canton-network/wallet-sdk`. |
| `dApp SDK` | Read from the npm `latest` dist-tag for `@canton-network/dapp-sdk`. |
| `Wallet Gateway` | Keep as manual/fallback from the Wallet Gateway Docker image package until package API access is confirmed. Wallet team guidance says not to use the npm package for this row. |
| `Min Protocol Version` | Keep as manual/fallback until a public live source is available. |
| `Migration ID` | Read from `synchronizer.active.migration_id` on the network's `/info` endpoint and validate against `sv.migration_id`. |
| `Splice DAR Versions` | Keep as manual/fallback. Release bundles show shipped DARs, but review on the original automation PR noted that they are not necessarily the DAR versions currently in use. |
| `Release Notes` | Link to the observed Splice release. |
| `Primary Scan API` | Static canonical `scan.sv-1...` endpoint for each network. |

### Generate external snippets

External snippet extraction from source repositories is documented in [config/snippet-config/update-workflows.md](config/snippet-config/update-workflows.md). Use that workflow when updating snippet configs under `config/snippet-config/` or regenerating checked-in snippets under `docs-main/snippets/external/`.

```bash
npm run generate:external-snippets -- --list
npm run generate:external-snippets -- canton --source-dir ../canton
```

### Generate the JSON API reference

This repo includes a checked-in source config for the Ledger API OpenAPI bundle inputs under `config/x2mdx/ledger-api/source-artifacts.json`.
The generator script refreshes the latest configured `openapi.yaml` from the Canton release bundle into the docs tree and rewires `docs-main/docs.json` so Mintlify renders the JSON API reference natively:

```bash
python3 scripts/generate_json_api_reference.py
```

or:

```bash
npm run generate:json-api-reference
```

By default this writes:

- `docs-main/openapi/json-ledger-api/openapi.yaml`
- `docs-main/docs.json`

The generated nav is published under `API Reference -> Ledger API -> OpenAPI`, using Mintlify's native generated endpoint pages under `reference/json-api-reference`. The legacy checked-in MDX page at `docs-main/reference/json-api-reference.mdx` is removed by the generator.

### Generate the JSON API AsyncAPI reference

This repo also includes a checked-in source config for the Ledger API AsyncAPI bundle inputs under `config/x2mdx/ledger-api-asyncapi/source-artifacts.json`.
The generator script downloads the configured Canton release bundles, extracts `asyncapi.yaml` into `.internal/cache/x2mdx/ledger-api-asyncapi/`, writes a local x2mdx manifest into `.internal/generated/x2mdx/ledger-api-asyncapi/manifest.json`, and then renders the MDX page through the docs repo `direnv` / `nix` shell.

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

This repo also includes a checked-in source config for the published Java bindings Javadoc jars at `config/x2mdx/ledger-bindings/source-artifacts.json`.
The generator script downloads those jars into `.internal/cache/x2mdx/ledger-bindings/`, writes a local x2mdx manifest into `.internal/generated/x2mdx/ledger-bindings/manifest.json`, and then renders the MDX pages through the docs repo `direnv` / `nix` shell.

Run:

```bash
python3 scripts/generate_ledger_bindings_api_reference.py
```

or:

```bash
npm run generate:ledger-bindings-api-reference
```

By default this writes:

- `docs-main/reference/java-bindings.mdx`
- `docs-main/reference/java/`
- `docs-main/docs.json`

The generated nav is added under the top-level `API Reference` dropdown as `Java Bindings -> Javadocs`, with each nested group populated directly from the generated Java package pages.

### Generate the Daml Standard Library reference

This repo also includes a checked-in source config for versioned Daml Standard Library docs JSON generation at `config/x2mdx/daml-standard-library/source-artifacts.json`.
The generator script uses local SDK artifacts via `dpm` or `daml` to build cached docs JSON snapshots under `.internal/cache/x2mdx/daml-standard-library/`, writes a local x2mdx manifest into `.internal/generated/x2mdx/daml-standard-library/manifest.json`, and then renders MDX pages through the docs repo `direnv` / `nix` shell.

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
The generator script discovers stable Canton versions from the source repo tags, downloads the matching `canton-open-source-<version>.tar.gz` bundles from `canton.io/releases`, extracts the published `protobuf/` tree under `.internal/cache/x2mdx/protobuf-history/`, compiles local descriptor images with `grpc_tools.protoc`, writes a local x2mdx manifest into `.internal/generated/x2mdx/protobuf-history/manifest.json`, and then renders MDX pages through the docs repo `direnv` / `nix` shell.

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
The generator script downloads the configured tarballs into `.internal/cache/x2mdx/typescript-bindings/`, installs local package dependencies, renders TypeDoc JSON into `.internal/generated/x2mdx/typescript-bindings/`, writes a local x2mdx manifest, and then rewrites the checked-in Mintlify page through the docs repo `direnv` / `nix` shell.

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

The generator also adds that page under the top-level `API Reference` dropdown as `TypeScript -> @daml/types`.

### Generate the Wallet Gateway JSON-RPC reference

This repo also includes a checked-in source config for versioned Wallet Gateway OpenRPC specs from `hyperledger-labs/splice-wallet-kernel` at `config/x2mdx/wallet-gateway-openrpc/source-artifacts.json`.
The generator script discovers versions from GitHub releases filtered to the `@canton-network/wallet-gateway-remote@` release stream, clones or fetches a cached bare repo under `.internal/cache/x2mdx/wallet-gateway-openrpc/`, materializes local versioned OpenRPC JSON files from the matching tag snapshots, writes a local x2mdx manifest into `.internal/generated/x2mdx/wallet-gateway-openrpc/manifest.json`, and then renders MDX pages through the docs repo `direnv` / `nix` shell.

Run:

```bash
python3 scripts/generate_wallet_gateway_openrpc_reference.py
```

or:

```bash
npm run generate:wallet-gateway-openrpc-reference
```

### Generate the Splice Mintlify OpenAPI specs

This repo also includes a dedicated wrapper that fetches the configured Splice OpenAPI specs from published decentralized-canton-sync `*_openapi.tar.gz` release bundles and writes the managed source files under `docs-main/openapi/splice/`, so Mintlify can render them natively. The wrapper only updates `docs-main/docs.json` for specs listed in `config/mintlify-openapi/splice-openapi/source-artifacts.json` under `enabled_nav_specs`.

Run:

```bash
python3 scripts/generate_splice_mintlify_openapi.py
```

or:

```bash
npm run generate:splice-mintlify-openapi
```

By default this writes:

- `docs-main/openapi/splice/`
- `docs-main/docs.json` only when one or more specs are enabled in `enabled_nav_specs`

Enabled specs are added under the top-level `API Reference` dropdown as `Splice APIs`, with Mintlify-rendered OpenAPI entries grouped under `Scan APIs`, `Validator APIs`, and `Token Standard APIs`.


## Provide Feedback on a Page

Every page on docs.canton.network has two feedback buttons in the footer:
- `Suggest edits`
- `Raise issue`

### Suggest edits:
Use this to propose a direct change to the page, fix a typo, update a code sample, improve wording, etc.

**How it works:**

- Click “Suggest edits” in the footer of any page.
- GitHub opens the source file for that exact page.
- Fork the repo, make your edits, and open a Pull Request.
- Canton docs team reviews and merges accepted changes if all checks out.

### Raise Issue:
Use this to report a problem or request new content without editing the source yourself.

**How it works:**

- Click “Raise Issue” in the footer of any page.
- A GitHub Issue opens *Pre-filled* with the Path of the page you were on.
- Describe in detail what's wrong or missing along with the source of information to verify and submit.
- The team reviews it and responds.
