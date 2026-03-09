# CNU OpenAPI Lifecycle MVP

Build a lifecycle JSON for Canton Network Utilities OpenAPI specs across clean semver release tags.

## What it tracks

- Specs discovered from release tags (`^(v)?X.Y.Z$`)
- Entity lifecycle per spec:
  - `path`
  - `operation` (`METHOD /path`)
  - `component` (`components.<kind>.<name>`)
  - `tag`
- Lifecycle metadata:
  - `introduced_version`
  - `changed_in_versions`
  - `removed_version`

## Run

```bash
cd /Users/danielporter/new-docs
python3 scripts/cnu_openapi_lifecycle_mvp.py \
  --repo /Users/danielporter/canton-network-utilities \
  --output .internal/generated/cnu-openapi-lifecycle-mvp.json
python3 scripts/render_cnu_openapi_lifecycle_mdx.py \
  --input .internal/generated/cnu-openapi-lifecycle-mvp.json \
  --overview docs-main/utilities/reference/splice-apis.mdx \
  --specs-dir docs-main/utilities/reference/splice-api-specs \
  --docs-json docs.json \
  --update-docs-json
```

Exclude specs by canonical id:

```bash
python3 scripts/cnu_openapi_lifecycle_mvp.py \
  --repo /Users/danielporter/canton-network-utilities \
  --output .internal/generated/cnu-openapi-lifecycle-mvp.json \
  --exclude-spec '^cn-validator/|neuchatel'
python3 scripts/render_cnu_openapi_lifecycle_mdx.py \
  --input .internal/generated/cnu-openapi-lifecycle-mvp.json \
  --overview docs-main/utilities/reference/splice-apis.mdx \
  --specs-dir docs-main/utilities/reference/splice-api-specs \
  --docs-json docs.json \
  --exclude-spec '^cn-validator/|neuchatel' \
  --clean-specs-dir \
  --update-docs-json
```

Exclude by source file path (before canonical remapping):

```bash
python3 scripts/cnu_openapi_lifecycle_mvp.py \
  --repo /Users/danielporter/canton-network-utilities \
  --output .internal/generated/cnu-openapi-lifecycle-mvp.json \
  --exclude-source '/cn-validator/|/neuchatel\\.yaml$'
```

Default tag filter is `^(v)?0\.[0-9]+\.[0-9]+$` (the `v0.x.y` release line).

## Narrow scope while iterating

```bash
python3 scripts/cnu_openapi_lifecycle_mvp.py \
  --repo /Users/danielporter/canton-network-utilities \
  --output .internal/generated/cnu-openapi-lifecycle-mvp.scan.json \
  --include-spec 'cn-validator/scan' \
  --max-tags 12
```

To include all clean semver tags (including non-`v0` streams):

```bash
python3 scripts/cnu_openapi_lifecycle_mvp.py \
  --repo /Users/danielporter/canton-network-utilities \
  --output .internal/generated/cnu-openapi-lifecycle-all-semver.json \
  --tag-regex '^(v)?[0-9]+\.[0-9]+\.[0-9]+$'
```

## Notes

- The script uses `yq` to parse YAML (`yq -o=json`).
- Known path migrations are normalized so lifecycle continuity is preserved:
  - `cn-token-standard/*` -> `cn-validator/*`
  - `cn-validator/scan-internal.yaml` -> `cn-validator/scan.yaml`
  - legacy `utility-token-standard/*.yaml` -> `utility-token-standard/v1/*-v1.yaml`
  - allocation-instruction variants are rolled up to one canonical spec id
- The renderer creates Mintlify-compatible MDX pages and can wire them into `docs.json`.
- Spec pages include endpoint reference details from the latest available OpenAPI version (method/path, params, request body, responses).
