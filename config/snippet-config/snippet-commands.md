# Snippet commands

Run from the cf-docs root in its direnv/Nix environment. Examples use `splice`;
replace the repository, checkout, source path, and `example` name as needed.
Authoring updates only `main` snippets.

For add/edit, the source file must be tracked and unchanged at HEAD, with an
exact remote-tracking ref pointing to HEAD (fetch or push first).
Append `--dry-run` to preview validated changes without writing.

## Add

```bash
npm run snippets:add -- splice --source-dir ../splice --source apps/example.yaml --name example
```

Paste the printed import and component into your MDX page. Add `--marker DEMO`
to extract between `DEMO_START` and `DEMO_END`; omit it for the whole file.

To change an existing selector or language while keeping its name:

```bash
npm run snippets:edit -- splice example --source-dir ../splice --marker DEMO
```

Review and commit the manifest, source lock, generated MDX, and any page edits.
