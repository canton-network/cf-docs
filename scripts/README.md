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
  --output-dir docs-main/appdev/reference/daml-prim-api
```

### Update docs navigation (`docs.json`)

```bash
python3 scripts/daml_docs_json_to_mdx.py \
  --input-json /path/to/daml-prim.json \
  --output-dir docs-main/appdev/reference/daml-prim-api \
  --docs-json docs.json \
  --nav-group-name "Generated API Reference" \
  --nav-dropdown-name "App Development" \
  --create-nav-group-if-missing
```

The converter updates every navigation group named `Generated API Reference`.

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
2) convert JSON to MDX
3) update `docs.json` navigation

```bash
./scripts/sync_daml_prim_api_from_dpm.sh \
  --sdk-version 3.4.10 \
  --lf-target 2.2
```

Use an existing JSON file instead:

```bash
./scripts/sync_daml_prim_api_from_dpm.sh \
  --input-json /tmp/daml-prim.json
```

### Test

```bash
python3 -m unittest -v scripts.tests.test_daml_docs_json_to_mdx
```
