# Contributing to Canton Network Docs

Thanks for helping improve [docs.canton.network](https://docs.canton.network).

This repo is the **home for Canton Network documentation** and content here should reflect the current, correct behavior of the latest Canton, Daml, and Splice releases.

## Before you start

- **Search existing [issues](https://github.com/canton-network/cf-docs/issues) and [PRs](https://github.com/canton-network/cf-docs/pulls) first** to avoid duplicate work.

- We prioritize PRs that fix inaccuracies, clarify confusing concepts, or add missing information. To minimize merge conflicts, PRs consisting solely of cosmetic reformatting may be closed.

- **Check the information in your PR against the current release** before writing or editing a page, confirm the behavior, APIs, config, and defaults you're describing match the latest Canton and Splice releases. If you're documenting something version specific, say so explicitly rather than leaving it ambiguous.

- **Verify every technical claim:** an AI-generated draft might hallucinate or invent details. Always check API signatures, CLI flags, config keys, version numbers, and code samples against the Actual Current Canton/Splice/Daml Release or source docs. Do not assume the model's output reflects the current release, and make sure to review everything before opening a PR.

## Ways to contribute

### Provide Feedback on a Docs Page

Every page on docs.canton.network has two feedback buttons in the footer:

- `Suggest edits`
- `Raise issue`

<img width="340" height="77" alt="Suggest edits and Raise issue buttons in the page footer" src="https://github.com/user-attachments/assets/e143643a-484a-43a3-a4cb-b6ccda5f4fef" />

#### Suggest edits

Use this to propose a direct change to the page, fix a typo, update a code sample, improve wording, etc.

**How it works:**

- Click "Suggest edits" in the footer of any page.
- GitHub opens the source file for that exact page.
- Fork the repo, make your edits, and open a Pull Request.
- Canton docs team reviews and merges accepted changes if all checks out.

#### Raise Issue

Use this to report a problem or request new content without editing the source yourself.

**How it works:**

- Click "Raise Issue" in the footer of any page.
- A GitHub Issue opens *pre-filled* with the path of the page you were on.
- Describe in detail what's wrong or missing along with the source of information to verify, and submit.
- The team reviews it and responds.

> **Alternatively, you can file an issue directly in the github repo here: https://github.com/canton-network/cf-docs/issues**

### Larger changes: PR from a local checkout

For new pages, restructuring, or anything touching multiple files, set up a local checkout, preview your changes with `mintlify dev`, and run `mintlify broken-links` before opening a PR.

#### Prerequisites

Either:

- [`direnv`](https://direnv.net/)
- [`nix`](https://nixos.org/download/) with `nix-command` and flakes support

OR:

- [Node.js 24](https://nodejs.org/en/download) (note that `mintlify` is not currently compatible with Node.js 26)
- [Python 3.14](https://www.python.org/downloads/) if you are running any of the machinery for syncing snippets or updating generated docs

#### Running the dev server

```bash
direnv allow
cd docs-main && mintlify dev
```

The site will be available at <http://localhost:3000>.

#### Check for broken links

```bash
mintlify broken-links
```

### Missing developer tooling

**This repository is strictly for core network documentation, not a tooling directory.** If you want to add a third-party wallet, SDK, indexer, explorer, or partner tool, please submit it to the [Canton Developer Hub](https://dev-hub.canton.foundation/). All external tooling is maintained in that repository to ensure it is properly reviewed and tagged.

Open a PR there to add your tool. Maintaining external tooling in the Dev Hub ensures it can be properly reviewed, tagged, and featured on the new docs overview page.

## Content and style guidelines

- Match the tone and structure of the surrounding pages in `docs-main/` don't introduce a new voice or format for a single page.

- Prefer editing an existing page over creating a new one if the topic already has a home.

- Keep code samples runnable and tested against current SDK/CLI versions.

- If a page is generated or synced from an external source, refer to the 'Generate external snippets' section in `cf-docs/README.md`. Do not hand-edit the generated output. Instead, update the source or the snippet config in `config/snippet-config/`.

- Links should be relative and verified with `mintlify broken-links`.

### Handling version divergence

Canton Network docs track the current MainNet, TestNet, and DevNet releases. Check the [Version Compatibility Dashboard](https://docs.canton.network/shared/version-compatibility-dashboard) for which Canton/Splice versions each net is actually on before assuming a version pin — don't copy a version number from another page, and don't hardcode a table of pins into a guide like this one, since it goes stale as soon as a net upgrades.

**Default to latest.** When you're not told otherwise, write against the latest upstream version and verify it against the current release, not whatever version an existing sibling page happens to be pinned to.

**When behavior, config, or output genuinely differs between Canton versions still live on a supported net**, don't silently describe only one of them and don't duplicate the whole page. Use Mintlify's `<Tabs>` component to branch the diverging section, with one `<Tab>` for the current major Canton version (e.g. `3.5.x`) and one for the previous major version (e.g. `3.4.x`), defaulting to the tab for the current major version. Content pulled from upstream inside a tab keeps its own `{/* COPIED_START ... COPIED_END */}` markers, scoped to that tab. See `global-synchronizer/production-operations/key-management.mdx` for a worked example (Offline Root Namespace Key tabbed 3.5/3.4, Online Root Namespace Key left untabbed since it hasn't diverged).

**For snippets pulled from upstream**, the source path tells you whether it's versioned:
- `{repo}:docs-open/...` sources track a repo's `main` branch and are not version-pinned — use these for content that doesn't diverge across supported Canton releases.
- `docs-website:docs/replicated/{repo}/{version}/...` sources are pinned to a specific release branch (e.g. `3.4`, `3.5`) — use these when the content is expected to diverge, and pull the matching version for each `<Tab>`.

See [config/snippet-config/update-workflows.md](config/snippet-config/update-workflows.md) for the extraction mechanics (`--version` flag, output location under `snippets/external/{repo}/{version}/`).

## Licensing

By contributing, you agree your changes are licensed under this repo's license model, for more info see the [README](https://github.com/canton-network/cf-docs/blob/main/README.md) for details.

## Review process

- A member of the Canton docs team will review your PR for accuracy, value, and fit with existing content. We aim to do this within a week, but appreciate your patience if there are slight delays depending on the team's workload.
  
  If you have been collaborating with someone from the Canton team, please @mention them in your PR description so we can assign the right SME and make the review faster.

- Expect feedback if a change is out of date with the current release, etc.

  Note: If any further queries or review questions in a PR get no response for more than a week, that PR will be closed immediately.

- Once approved and checks pass, the docs team merges.

Questions about where something belongs, or whether a change is worth making? Open a [Discussion](https://github.com/canton-network/cf-docs/discussions) before doing the work.
