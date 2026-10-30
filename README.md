# Canton Network Docs

This repo manages the contents of the [docs.canton.network](https://docs.canton.network) website.

Copyright (c) 2026 Canton Network. All rights reserved.
SPDX-License-Identifier: Apache-2.0 AND CC-BY-4.0


## Provide Feedback on a Docs Page

Every page on docs.canton.network has two feedback buttons in the footer:
- `Suggest edits`
- `Raise issue`

<img width="340" height="77" alt="image" src="https://github.com/user-attachments/assets/e143643a-484a-43a3-a4cb-b6ccda5f4fef" />

### Suggest edits:
Use this to propose a direct change to the page, fix a typo, update a code sample, improve wording, etc.

**How it works:**

- Click “Suggest edits” in the footer of any page.
- GitHub opens the source file for that exact page.
- Fork the repo, make your edits, and open a Pull Request.
- Canton docs team reviews and merges accepted changes if all checks out.

### Raise Issue:
Use this to report a problem or request new content without editing the source yourself.

**How it works:**

- Click “Raise Issue” in the footer of any page.
- A GitHub Issue opens *Pre-filled* with the Path of the page you were on.
- Describe in detail what's wrong or missing along with the source of information to verify and submit.
- The team reviews it and responds.


## Local Development

### Prerequisites

Either:

- [`direnv`](https://direnv.net/)
- [`nix`](https://nixos.org/download/) with `nix-command` and flakes support

OR:

- [Node.js 24](https://nodejs.org/en/download) (note that `mintlify` is not currently compatible with Node.js 26)
- [Python 3.14](https://www.python.org/downloads/) if you are running any of the machinery for syncing snippets or updating generated docs

### Authoring and generated content

Edit pages, navigation, and images in `docs-main/`, either directly or through
the Mintlify editor. Ordinary content has no separate source copy and is not
rewritten by documentation generation.

Pages with network-dependent sections are generated from page templates in
`docs-main/src/`. Each template sits at the same relative path as the page it
renders, so `docs-main/src/global-synchronizer/deployment/kubernetes-deployment.mdx`
renders `docs-main/global-synchronizer/deployment/kubernetes-deployment.mdx`.
Generated pages start with a `Generated from /src/...` comment; edit the
template, not the generated page. Templates are hidden pages (`hidden: true`,
listed under the hidden "Page templates" product in `docs.json`) so the Mintlify
editor can open them without publishing them in navigation, search, or the sitemap.

Inside a template, wrap network-dependent content in a single tab,
`<Tabs>` / `<Tab title="All networks">`, which the Mintlify editor can edit. Use
`|token|` placeholders for values from the version dashboard data and
`<div data-network-only="devnet,testnet">` for network-specific content. Run
`npm run generate:network-variable-tabs` to render one tab per network into the
generated page. To add a template, copy the page into `docs-main/src/`, add
`hidden: true` to its frontmatter, and add it to the "Page templates" product.
Edit generated reference pages through their owning generators, as before.

For generated API lifecycle settings, see the [examples and accepted values](config/x2mdx/lifecycle.md).

Run `npm run validate:network-variable-tabs` to check generated pages without
modifying files. Direct edits to a generated page fail validation; edit its
template instead. On pull requests, CI also posts a comment naming the template
to edit and quoting lines that exist only in the generated page. Ordinary page edits and new images do not require
regeneration.

### Running the dev server

```bash
direnv allow
cd docs-main && mintlify dev
```

The site will be available at http://localhost:3000.

### Check for broken links

```bash
mintlify broken-links
```

## Update generated docs

The [Update generated docs](.github/workflows/update-version-dashboard.yml) workflow
runs every two hours. It regenerates each target in turn and opens or updates one
PR per target that changed.

To run it outside the schedule, use **Run workflow** on the workflow's Actions page,
or:

```bash
gh workflow run "Update generated docs" -R canton-network/cf-docs --ref main
gh workflow run "Update generated docs" -R canton-network/cf-docs --ref main \
  -f targets="canton-metrics-reference daml-script"
```

`targets` defaults to `all`; otherwise pass space-separated target keys. Set
`-f dry_run=true` to list the selected commands without generating or opening PRs.
To list target keys locally:

```bash
python3 scripts/update_generated_reference_prs.py --targets all --print-targets-json
```

Only one run executes at a time. A dispatch made while a run is in progress waits
for it, and a newer waiting run replaces an older waiting one. To restart instead,
cancel the in-progress run first (`gh run cancel <run-id> -R canton-network/cf-docs`).
Cancellation can take several minutes to stop the remaining matrix jobs.

## Generate external snippets

External snippet extraction from source repositories is documented in [config/snippet-config/update-workflows.md](config/snippet-config/update-workflows.md). Use that workflow when updating snippet configs under `config/snippet-config/` or regenerating checked-in snippets under `docs-main/snippets/external/`.

Run this whenever you add, remove, or update a snippet source in `config/snippet-config/`, or when you need to pull in changes from an upstream repo (such as Canton or Splice) that are referenced by existing snippets.

```bash
npm run generate:external-snippets -- --list
npm run generate:external-snippets -- canton --source-dir ../canton
```

## License

This repository uses a dual-license model:

- **Documentation prose** (`.mdx` files, text content): [Creative Commons Attribution 4.0 International (CC-BY-4.0)](https://creativecommons.org/licenses/by/4.0/) — see [LICENSE-DOCS](LICENSE-DOCS)
- **Code snippets and configuration** (embedded code examples, scripts, JSON config): [Apache License 2.0](http://www.apache.org/licenses/LICENSE-2.0) — see [LICENSE](LICENSE)
