# DAML Doc Lifecycle MVP

Build one consolidated API lifecycle JSON from versioned published docs.

## Run

```bash
cd /Users/danielporter/new-docs
direnv allow   # first time per clone
python3 scripts/daml_doc_lifecycle_mvp.py \
  --config config/daml-doc-lifecycle-mvp.sample.json \
  --output .internal/generated/daml-doc-lifecycle-mvp.json
python3 scripts/render_daml_doc_lifecycle_mdx.py \
  --input .internal/generated/daml-doc-lifecycle-mvp.json \
  --overview docs-main/appdev/modules/m4-ledger-bindings-api-lifecycle.mdx \
  --details-dir docs-main/appdev/reference/ledger-bindings-api-lifecycle
```

## Preview In Mintlify (via Nix toolchain)

```bash
cd /Users/danielporter/new-docs
direnv exec . npx mintlify dev
```

## Output

The generated JSON contains:

- per-symbol `introduced_version`
- per-symbol `deprecated_version` (Java best-effort, Scala not inferred in this MVP)
- per-symbol `removed_version`
- version-specific doc links for each symbol

The generated Mintlify pages are:

- `docs-main/appdev/modules/m4-ledger-bindings-api-lifecycle.mdx`
- `docs-main/appdev/reference/ledger-bindings-api-lifecycle/*.mdx` (artifact pages)
- `docs-main/appdev/reference/ledger-bindings-api-lifecycle/*-types/*.mdx` (per-type reference pages)
