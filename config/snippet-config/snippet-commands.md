# Snippet commands

Add `--dry-run` to any snippet command to preview changes without writing.

## Register a repository

```bash
npm run snippets:add-repo -- dpm
```

This creates `config/snippet-config/dpm-snippet-list-remote.json`. Register each repository once, before adding its first snippet; the checkout must already exist.

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

To re-render every snippet from a repository, for example after an upstream
release, omit the snippet name:

```bash
npm run snippets:edit -- canton --source-dir ../canton
```

Only generated MDX that changed is written; the manifest is left alone. If any
source is missing, the command lists the missing files and writes nothing. Canton
snippets read generated files, so first run
`sbt "docs-open / reset" "docs-open / generateSphinxSnippets"` in the Canton checkout.

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

## Open pull requests

Use one cf-docs PR per logical change; registration can share the first snippet's
PR. Include the changed manifest, generated MDX, and page imports or removals.
Source files and marker changes belong in a PR to the source repository.

| Tutorial | PRs needed |
| --- | --- |
| Register | cf-docs only. |
| Add | cf-docs; also the source repo if adding or changing source or markers. |
| Edit | cf-docs; also the source repo if its content changed. Selector/language-only edits need only cf-docs. |
| Move | cf-docs; also the source repo if its file was moved or renamed. |
| Delete | cf-docs only; the command leaves source files and markers in place. |

Commit and push a feature branch (here `codex/snippet-example`) in each affected
repo. The Add, Edit, and Move examples above change `dpm`, so they need both PRs.
For the Add example, run these from cf-docs after pushing both branches.

Create the source PR first:

```bash
(cd ../dpm && gh pr create --repo digital-asset/dpm --base main --head codex/snippet-example --fill)
```

Then create the cf-docs PR. Replace `SOURCE_PR_URL` with the link printed above;
omit `--body` for a docs-only change:

```bash
gh pr create --repo canton-network/cf-docs --base main --head codex/snippet-example --fill --body "Source PR: SOURCE_PR_URL"
```

For Add, Edit, and Move, merge the source PR before the cf-docs PR. If separately
removing source files or markers after Delete, merge the cf-docs removal first.
For a fork, use `--head YOUR_USER:codex/snippet-example` and keep `--repo` pointing
to the upstream repository.

## Generate snippets

`snippets:add`, `snippets:edit`, and `snippets:move` already extract MDX. Each command reads the repository manifest under `config/snippet-config/`, runs the extraction helper against your local source checkout, and writes only changed files under `docs-main/snippets/external/<repo>/main/`. There is no separate copy step.

To regenerate every snippet for a repository after an upstream change:

```bash
npm run snippets:edit -- dpm --source-dir ../dpm
npm run snippets:edit -- canton --source-dir ../canton
```

Omit the snippet name so the command walks the whole manifest. Use `--dry-run` to preview diffs without writing. If any recorded source is missing, the command lists the paths and writes nothing. Canton snippets depend on generated Sphinx inputs, so run this first in the Canton checkout:

```bash
sbt "docs-open / reset" "docs-open / generateSphinxSnippets"
```

Update note: The old `npm run generate:external-snippets` wrapper and its `--copy-output` flag are gone. Bulk refresh is `snippets:edit` without a snippet name, and output lands directly in the docs tree.

For low-level extraction only (for example in a source-repo CI job), run the helper against an export config. By default it writes to that repo's `docs-output/`:

```bash
node scripts/helpers/generateOutputDocs.js --verbose
# or from a source checkout that vendors the helper:
node scripts/docs/generateOutputDocs.js --verbose
```

Optional flags: `--repo-root`, `--export-config`, `--output`. Prefer the `snippets:*` npm commands when updating checked-in docs in this repository.
