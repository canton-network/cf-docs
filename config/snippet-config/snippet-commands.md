# Snippet commands

Run from the cf-docs root with Python 3.14 and Node.js 24, or the repository's
direnv/Nix environment. These tutorials assume a `dpm` checkout at `../dpm`;
substitute your repository key and checkout path as needed.

Commands read your current local source, including uncommitted edits, and update
only `main` snippets under `docs-main/snippets/external/<repo>/main/`.
Add `--dry-run` to any command to preview changes without writing.

## Register a repository

```bash
npm run snippets:add-repo -- dpm
```

This creates `config/snippet-config/dpm-snippet-list-remote.json`. Register each
repository once, before adding its first snippet; the checkout must already exist.

## Add a snippet

Create a small source file, then extract it:

```bash
printf 'message: hello\n' > ../dpm/example.yaml
npm run snippets:add -- dpm --source-dir ../dpm --source example.yaml
```

The command creates `dpm-literal-full-example.mdx` and prints the page import
and component usage. Paste both into a documentation page to display the snippet.
`--source` is relative to the source checkout; omitting `--marker` extracts the
whole file. To extract a section, surround it with `# EXAMPLE_START` and
`# EXAMPLE_END` comments and add `--marker EXAMPLE`.

## Edit a snippet

Change the original source, then re-render the existing snippet:

```bash
printf 'message: goodbye\n' > ../dpm/example.yaml
npm run snippets:edit -- dpm dpm-literal-full-example --source-dir ../dpm
```

The snippet name and page imports stay unchanged. Use `--marker NAME` or
`--full-file` to change the selection, and `--language LANG` to change the fence.
For existing snippets, use the name recorded in the repository's manifest.

## Move a snippet's source

Rename the source file, then update its mapping:

```bash
mv ../dpm/example.yaml ../dpm/renamed.yaml
npm run snippets:move -- dpm dpm-literal-full-example --source-dir ../dpm --source renamed.yaml
```

The snippet is re-rendered from the new path; its name and page imports stay
unchanged.

## Delete a snippet

Remove its imports and component usages from documentation pages, then run:

```bash
npm run snippets:delete -- dpm dpm-literal-full-example
```

Deletion refuses while a page still references the snippet and lists those
references. Otherwise it removes the manifest entry and generated MDX, leaving
the original source file and repository manifest in place.
