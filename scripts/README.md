# Scripts

## Daml JSON to MDX converter (`daml_docs_json_to_mdx.py`)

Use `scripts/daml_docs_json_to_mdx.py` to convert `damlc docs --format json` output into Mintlify MDX pages.

### Inputs and outputs

- Input: JSON file produced by `damlc docs --format json` (for example `daml-prim.json`).
- Output: one `.mdx` file per module plus an index page.

### Basic usage

```bash
python3 scripts/daml_docs_json_to_mdx.py \
  --input-json /path/to/daml-prim.json \
  --output-dir docs-main/daml-reference/daml-prim-api
```

### Update docs navigation (`docs.json`)

For this repo's Daml Prim docs flow, use `sync_daml_prim_api_from_dpm.sh` below.

`daml_docs_json_to_mdx.py --docs-json` is a generic group-page replacement mode:

```bash
python3 scripts/daml_docs_json_to_mdx.py \
  --input-json /path/to/daml-prim.json \
  --output-dir docs-main/daml-reference/daml-prim-api \
  --docs-json docs.json \
  --nav-group-name "Existing Group Name" \
  --nav-dropdown-name "Existing Dropdown Name" \
  --create-nav-group-if-missing
```

The converter updates every matching group under the selected dropdown.

### Common options

- `--index-file`: customize index filename (default `index.mdx`).
- `--nav-base`: set explicit navigation path prefix for `docs.json`.
- `--nav-dropdown-name`: scope docs.json updates to one dropdown.
- `--create-nav-group-if-missing`: upsert the group under the selected dropdown.

## Generate daml-prim JSON from dpm (`generate_daml_prim_json_from_dpm.sh`)

This script generates Daml docs JSON directly from installed `dpm` SDK artifacts.

```bash
./scripts/generate_daml_prim_json_from_dpm.sh \
  --output-json /tmp/daml-prim.json \
  --sdk-version 3.4.10 \
  --lf-target 2.2 \
  --package-set prim \
  --sdk-source dpm
```

Notes:
- If `--sdk-version` is omitted, it defaults to `latest` from `https://get.digitalasset.com/install/latest`.
- If `--lf-target` is omitted, it auto-picks the highest numeric LF target present in the installed package DB.
- Use `--skip-install` if the SDK is already installed and you want a faster local iteration loop.
- `--sdk-source` controls where SDK artifacts come from:
  - `daml`: `~/.daml/sdk/<version>` + direct `damlc docs`
  - `dpm`: `~/.dpm/cache/...` + `dpm damlc docs`
  - `dpm` (default)
  - `auto`: prefer `dpm`, then fallback to `daml`
- `--package-set` controls source modules:
  - `prim`: `daml-prim` modules only.
  - `stdlib`: `daml-stdlib` modules only.
  - `base`: `daml-stdlib + daml-prim` merged by module name (stdlib takes precedence), matching the docs pipeline composition.

To match the docs pipeline module set:

```bash
./scripts/generate_daml_prim_json_from_dpm.sh \
  --output-json /tmp/daml-base.json \
  --sdk-version 3.4.11 \
  --lf-target 2.2 \
  --package-set base \
  --skip-install
```

## End-to-end sync from dpm (`sync_daml_prim_api_from_dpm.sh`)

This script runs the full flow:
1) generate JSON via `dpm damlc docs --format json`
2) analyze multiple SDK versions (latest 3 per family by default) for enrichment metadata
3) publish exactly one docs tree (latest by default) to `docs-main/daml-reference/daml-prim-api`
4) update `docs.json` under `App Development` group `Daml Standard Library`
5) remove legacy `Generated API Reference` groups and remove `Daml Reference Docs` dropdown

```bash
./scripts/sync_daml_prim_api_from_dpm.sh
```

By default this analyzes versions selected from GitHub releases (`digital-asset/daml`):
- latest 3 from `3.4.x`
- latest 3 from `3.3.x`
- latest 3 from `3.2.x`

and publishes the latest selected version.

For each family, selection keeps recent versions and includes a historical sample so lifecycle
changes (introduced/removed modules) are captured in the published output.

Specify exact versions:

```bash
./scripts/sync_daml_prim_api_from_dpm.sh --versions 3.4.11,3.4.10,3.4.9 --publish-sdk-version 3.4.11
```

Use an existing JSON file instead:

```bash
./scripts/sync_daml_prim_api_from_dpm.sh \
  --input-json /tmp/daml-prim.json \
  --sdk-version 3.4.10
```

Notes:
- `--input-json` supports single-version mode only.
- Output path defaults to `docs-main/daml-reference/daml-prim-api`.
- Override analyze count per family via `--latest-n N`.
- Override default families via `--minor-families CSV` (for example `3.4,3.3,3.2`).
- Override SDK artifact source via `--sdk-source daml|dpm|auto` (default `dpm` in sync script).
- `--lf-target` and `--skip-install` are forwarded to JSON generation.
- `--publish-sdk-version` lets you publish a specific analyzed SDK version.
- Removed modules are retained as historical pages and marked `removed in <version>` in the index.

## Navigation cleanup helper (`cleanup_daml_reference_docs_nav.py`)

This helper removes legacy nav structures used by older generated-docs flows:
- removes top-level dropdown `Daml Reference Docs`
- removes `Generated API Reference` groups from `App Development` versions

```bash
python3 scripts/cleanup_daml_reference_docs_nav.py --docs-json docs.json
```

## Diff two JSON outputs (`diff_daml_docs_json.py`)

Use this when you want to compare two `damlc docs --format json` outputs.

It reports:
- byte-level/raw differences (size + sha256)
- semantic API differences (modules, functions, ADTs, classes, class methods)
- schema/format differences (JSON path type changes and object key-set changes)

```bash
python3 scripts/diff_daml_docs_json.py \
  --old-json /tmp/prim-3.2.json \
  --new-json /tmp/prim-3.4.json
```

## Build unified Prelude docs across versions (`build_versioned_daml_prim_prelude.py`)

Use this to generate:
- one enriched JSON data file with per-element version timelines
- one unified MDX page for Prelude that includes interface-level change markers
  (introduced/removed/signature changes/deprecation changes)

```bash
python3 scripts/build_versioned_daml_prim_prelude.py \
  --version-json 3.2.0-snapshot=/tmp/prim-3.2.json \
  --version-json 3.4.11=/tmp/prim-3.4.json \
  --output-data docs-main/daml-reference/daml-prim-api/prelude-versioned.data.json \
  --output-mdx docs-main/daml-reference/daml-prim-api/prelude-versioned.mdx
```

### Test

```bash
python3 -m unittest -v scripts.tests.test_daml_docs_json_to_mdx
python3 -m unittest -v scripts.tests.test_list_latest_dpm_versions_by_family
python3 -m unittest -v scripts.tests.test_cleanup_daml_reference_docs_nav
python3 -m unittest -v scripts.tests.test_diff_daml_docs_json
python3 -m unittest -v scripts.tests.test_build_versioned_daml_prim_prelude
```
