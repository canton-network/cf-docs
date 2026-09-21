# Snippet commands

Run from the cf-docs root in its direnv/Nix environment. Examples use `splice`;
replace the repository key, checkout path, and source path as needed.
Authoring updates only `main` snippets.

## Add

```bash
npm run snippets:add -- splice --source-dir ../splice --source apps/example.yaml
```

Arguments:

- `repo` (positional): one of `canton`, `cn-quickstart`, `daml`, `daml-shell`, `splice`. Never inferred.
- `--source-dir`: local checkout of that repository. Required.
- `--source`: file path relative to the checkout.
- `--marker NAME`: extract between `NAME_START` and `NAME_END`; omit for the whole file.
- `--language`: code fence language; defaults from the file extension (`yaml`, `yml`, `json`, `sh`, `daml`, `scala`, `py`, `ts`, `js`, `rst`, `md`, `conf`, `sql`, `toml`).
- `--dry-run`: validate, print manifest and MDX diffs, write nothing.

The command runs the extractor on the new entry before writing anything. It
writes exactly two files: the repository manifest, with the entry inserted in
name order, and the generated MDX under `docs-main/snippets/external/<repo>/main/`.
Then it prints the import and component usage to paste into a page.

The snippet name is derived from the source path and marker. Names over 100
characters keep the first path segment, a six-character hash of the dropped
directories, the file stem, and the marker.

Uncommitted edits in the checkout are extracted as-is, so you can add markers
to a source file and preview the snippet before the upstream change lands.
Source provenance is not recorded yet.
