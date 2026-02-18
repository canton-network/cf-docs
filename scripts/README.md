# Scripts

## Daml JSON to MDX converter

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
  --nav-group-name "Generated API Reference"
```

The converter updates every navigation group named `Generated API Reference`.

### Common options

- `--index-file`: customize index filename (default `index.mdx`).
- `--nav-base`: set explicit navigation path prefix for `docs.json`.

### Test

```bash
python3 -m unittest -v scripts.tests.test_daml_docs_json_to_mdx
```
