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
  --output-dir docs-main/daml-reference/daml-prim-api/v3-4-10
```

### Update docs navigation (`docs.json`)

For this repo's Daml Prim docs flow, use `sync_daml_prim_api_from_dpm.sh` below.

`daml_docs_json_to_mdx.py --docs-json` is a generic group-page replacement mode:

```bash
python3 scripts/daml_docs_json_to_mdx.py \
  --input-json /path/to/daml-prim.json \
  --output-dir docs-main/daml-reference/daml-prim-api/v3-4-10 \
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

This script generates `daml-prim.json` directly from installed `dpm` SDK artifacts.

```bash
./scripts/generate_daml_prim_json_from_dpm.sh \
  --output-json /tmp/daml-prim.json \
  --sdk-version 3.4.10 \
  --lf-target 2.2
```

Notes:
- If `--sdk-version` is omitted, it defaults to `latest` from `https://get.digitalasset.com/install/latest`.
- If `--lf-target` is omitted, it auto-picks the highest numeric LF target present in the installed package DB.
- Use `--skip-install` if the SDK is already installed and you want a faster local iteration loop.

## End-to-end sync from dpm (`sync_daml_prim_api_from_dpm.sh`)

This script runs the full flow:
1) generate JSON via `dpm damlc docs --format json`
2) convert JSON to MDX for one or more SDK versions
3) update `docs.json` with a `Daml Reference Docs` dropdown and `Daml Prim API` version groups
4) remove legacy `Generated API Reference` groups from `App Development`

```bash
./scripts/sync_daml_prim_api_from_dpm.sh
```

By default this syncs the latest 3 stable SDK versions from `dpm version --all -o json`.

Specify exact versions:

```bash
./scripts/sync_daml_prim_api_from_dpm.sh --versions 3.4.11,3.4.10,3.4.9
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
- Override latest count via `--latest-n N`.
- `--lf-target` and `--skip-install` are forwarded to JSON generation.

### Test

```bash
python3 -m unittest -v scripts.tests.test_daml_docs_json_to_mdx
```
