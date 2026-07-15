# Contributing to Canton Network Docs

Thanks for helping improve [docs.canton.network](https://docs.canton.network).

This repo is the **home for Canton Network documentation** and content here should reflect the current, correct behavior of the latest Canton, Daml, and Splice releases.

## Before you start

- **Every change should create real value for a reader.** Fix something that's wrong, unclear, missing, or outdated but changes with cosmetic edits, reformatting for its own sake, or restructuring that doesn't improve clarity will be closed without merging.

- **Check it against the current release.** This is unified documentation. Before writing or editing a page, confirm the behavior, APIs, config, and defaults you're describing match the latest Canton and Splice releases.
If you're documenting something version specific, say so explicitly rather than leaving it ambiguous.

- **Search existing [issues](https://github.com/canton-network/cf-docs/issues) and [PRs](https://github.com/canton-network/cf-docs/pulls) first** to avoid duplicate work.

- **Verify every technical claim:** an AI-generated draft makes API signatures, CLI flags, config keys, version numbers, code samples against the actual current Canton/Splice/Daml behavior or source docs. Do not assume the model's output reflects the current release and make sure to review it all before hitting a PR. Models are frequently behind or simply wrong on fast-moving specifics.

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

### Larger changes: PR from a local checkout

For new pages, restructuring, or anything touching multiple files, set up a local checkout, preview your changes with `mintlify dev`, and run `mintlify broken-links` before opening a PR.

#### Prerequisites

Either:

- [`direnv`](https://direnv.net/)
- [`nix`](https://nixos.org/download/)

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

**This repo is for documentation, not a tooling directory.** If you want to list a wallet, SDK, indexer, explorer, or other third party developer/Partner tool that isn't represented yet, that will be at [Canton Developer Hub](https://dev-hub.canton.foundation/).

Open a PR there to add it and all external/partner tooling is maintained in that repo so it can be reviewed, tagged, and it's also currently added in new docs overview page.

## Content and style guidelines

- Match the tone and structure of the surrounding pages in `docs-main/` don't introduce a new voice or format for a single page.

- Prefer editing an existing page over creating a new one if the topic already has a home.

- Keep code samples runnable and tested against current SDK/CLI versions.

- If a page is generated or synced from an external source then see Generate external snippets from `cf-docs/README.md`, don't hand edit the generated output & update the source or the snippet config in `config/snippet-config/` instead.

- Links should be relative and verified with `mintlify broken-links`.

## Licensing

By contributing, you agree your changes are licensed under this repo's license model, for more info see the [README](/cf-docs/README.md) for details.

## Review process

- A member of the Canton docs team will review your PR for accuracy, value, and fit with existing content within a week of when open PR is submitted.

- Expect feedback if a change is out of date with the current release, etc.

- Once approved and checks pass, the docs team merges.

Questions about where something belongs, or whether a change is worth making? Open a [Discussion](https://github.com/canton-network/cf-docs/discussions) before doing the work.