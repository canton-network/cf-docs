# rst-to-mdx

A DPM component that converts reStructuredText documents into
Mintlify-compatible MDX files. Built for the migration from
`docs-website/docs/replicated/` (RST, Sphinx) to `docs/docs-main/` (MDX,
Mintlify), but the converter runs against any RST file on disk.

## Quick start

```bash
cd tools/rst-to-mdx
make build

# Convert one file
./rst-to-mdx path/to/input.rst path/to/output.mdx

# Or invoke through dpm — the local daml.yaml registers the component
# automatically when dpm runs from this directory.
dpm rst-to-mdx path/to/input.rst path/to/output.mdx

# Convert an entire RST tree to a mirror MDX tree in one command
./rst-to-mdx --batch \
  --input-dir <docs-website>/docs/replicated \
  --output-dir <output-mdx-tree> \
  --target-root <docs-main> \
  --copy-images

# Audit which RST files don't have a corresponding page in docs.json
./rst-to-mdx --audit-coverage \
  --docs-root <docs-website> \
  --target-root <docs-main>
```

## Input flexibility

The converter has no hard dependency on `docs-website/`. Any RST file
works as input, regardless of where it lives on disk. The only feature
that depends on `docs-website/` is **cross-reference resolution**:

| Situation | Cross-reference (`:ref:`, `:doc:`, etc.) behavior |
|---|---|
| Input lives somewhere under `docs-website/` | Auto-detected; the label index is built once and refs resolve to `/docs-main/<path>#<anchor>` URLs. |
| Input lives elsewhere, `--docs-root <path>` passed | Same as above using the explicit root. |
| Input lives elsewhere, no `--docs-root` | Refs become `[label](#TODO-resolve-…)` markers a human can resolve later. |

Every other transform — headings, inline formatting and roles, links
(named, anonymous, `:doc:`, `:download:`, autolinks like `<https://…>`),
code blocks, admonitions, `.. todo::` / `.. wip::` notes, images and
figures, lists, tables (list-table, csv-table, grid), Sphinx tabs,
`.. youtube::` and `.. raw:: html` video embeds, comments, frontmatter,
and provenance markers — runs identically regardless of input location.

## Heading mapping

Underline characters map to a fixed level (Canton's published CSS uses
the same rule):

| Underline  | Level |
|---|---|
| `#`        | H1 |
| `*` / `=`  | H2 |
| `-`        | H3 |
| `~`        | H4 |
| `^`        | H5 |
| `"`        | H6 |

Overlined+underlined headings render one level shallower than the same
character used as underline-only, capped at H1. So `### Title ###` and
`############` both produce H1; `*** Title ***` is H1; `--- Title ---`
is H2.

## CLI flags

```
rst-to-mdx <input.rst> [output.mdx] [flags]
rst-to-mdx --batch --input-dir <dir> --output-dir <dir> [flags]

  --title string          override auto-detected page title (default: first heading)
  --description string    set frontmatter description
  --source-label string   provenance source label (auto from path)
  --docs-root string      root of an RST docs tree for cross-ref resolution
                          (auto-detects `docs-website/` if input lives in one)
  --target-root string    target docs-main/ root for image copy and path
                          derivation (default "./docs-main")
  --copy-images           copy referenced images into target-root/images/docs_website/
  --strict                fail on unresolved :ref: or missing literalinclude
  --dry-run               print what would be written without touching disk
  -v, --verbose           show detailed conversion progress
      --version           print version and exit
```

### Common invocations

```bash
# Single file with image asset copy
./rst-to-mdx in.rst out.mdx --copy-images --target-root /tmp --verbose

# Override the auto-detected title
./rst-to-mdx in.rst out.mdx --title "Setting Up the Sandbox"

# Bail loudly on missing refs/files
./rst-to-mdx in.rst out.mdx --strict
```

## Directory layout

```
tools/rst-to-mdx/
├── component.yaml             # Unix DPM component manifest
├── component.windows.yaml     # Windows manifest (.exe path)
├── daml.yaml                  # local override-components for `dpm --help`
├── LICENSE                    # required at every published artifact root
├── cmd/rst-to-mdx/main.go     # Cobra CLI entrypoint
├── internal/
│   ├── convert/               # transform pipeline (one file per transform)
│   ├── include/               # .. include:: + .. literalinclude:: resolver
│   ├── labelindex/            # corpus walker that builds label → heading map
│   ├── navindex/              # docs.json walker so cross-refs land on real pages
│   └── pathmap/               # RST source path → MDX target path rules
├── smoke-test.sh              # end-to-end smoke against a real RST file
├── go.mod
├── Makefile
└── README.md
```

## Local DPM registration

Running `dpm --help` from inside `tools/rst-to-mdx/` picks up the
local `daml.yaml` and surfaces `rst-to-mdx` under "Dpm-SDK Commands"
without any install step. Useful for iterative development.

## Packaging and publishing

Cross-compile to all five supported platforms:

```
make release
```

That writes `dist/<os>-<arch>/` directories, each containing the
platform binary, a matching `component.yaml`, and a `LICENSE` file
(both required by the DPM publish validator).

Publish (DPM 1.0.12+ / SDK 3.5+):

```
dpm artifacts publish component \
  --name rst-to-mdx \
  --version 0.1.0-alpha \
  --platform darwin/arm64=./dist/darwin-arm64 \
  --platform darwin/amd64=./dist/darwin-amd64 \
  --platform linux/arm64=./dist/linux-arm64 \
  --platform linux/amd64=./dist/linux-amd64 \
  --platform windows/amd64=./dist/windows-amd64 \
  --registry oci://<target registry>
```

DPM 1.0.10 — 1.0.11 use the older form with the same flags:

```
dpm repo publish-component rst-to-mdx 0.1.0-alpha \
  -p darwin/arm64=./dist/darwin-arm64 \
  ... \
  --registry oci://<target registry>
```

Add `--dry-run` to validate without pushing.
