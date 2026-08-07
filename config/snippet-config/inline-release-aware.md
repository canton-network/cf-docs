# Inline release-aware snippets

Use this opt-in workflow when snippet content or its surrounding instructions must change with an upstream release. Existing manifest-backed snippets continue to use the legacy workflow until their pages are migrated.

## File model

Keep the canonical prose and snippet declarations together in a sibling authored file:

```text
validator.source.mdx  # edit this file
validator.mdx         # generated ordinary MDX; Mintlify reads this file
```

Never put `<IfVersion>` or the custom `<Snippet>` declaration directly in a Mintlify input without compiling it. The compiler removes the custom syntax and emits only the eligible prose and inert fenced code.

## Add a snippet

`snippets:add` is optional scaffolding. It validates the source and prints a declaration to paste where the snippet belongs; it does not create or edit a manifest.

For a released source:

```bash
npm run snippets:add -- \
  --source https://github.com/canton-network/splice/blob/2c941ea9e834d7602d388f3271c0f864025ea756/apps/app/src/pack/examples/sv-helm/validator-values.yaml \
  --marker SWEEP
```

For an upstream candidate:

```bash
npm run snippets:add -- \
  --source https://github.com/canton-network/splice/pull/6123 \
  --path apps/app/src/pack/examples/sv-helm/validator-values.yaml \
  --marker SWEEP
```

`--marker SWEEP` expands to `startAfter="SWEEP_START"` and `endBefore="SWEEP_END"`. Omit it for a complete file, or pass explicit `--start-after` and `--end-before`. The language is inferred from common extensions; use `--language` when inference is impossible.

## Version prose and snippet together

The candidate PR is declared in the page, so preview does not require a PR-number argument:

```mdx
<IfVersion
  repository="https://github.com/canton-network/splice"
  containsPullRequest={6123}
>
  Use the wallet sweep configuration introduced in this release.

  <Snippet
    source="https://github.com/canton-network/splice/pull/6123"
    path="apps/app/src/pack/examples/sv-helm/validator-values.yaml"
    startAfter="SWEEP_START"
    endBefore="SWEEP_END"
    language="yaml"
  />
<Else>
  Use the existing validator configuration.

  <Snippet
    source="https://github.com/canton-network/splice/blob/2c941ea9e834d7602d388f3271c0f864025ea756/apps/app/src/pack/examples/sv-helm/validator-values.yaml"
    startAfter="SWEEP_START"
    endBefore="SWEEP_END"
    language="yaml"
  />
</Else>
</IfVersion>
```

After squash merge, the resolver asks GitHub for PR `6123`'s actual merge commit. For a Splice release `X.Y.Z`, it resolves the source tag `X.Y.Z`, requires the public artifact release `vX.Y.Z`, and checks that the merge commit is an ancestor of the source release commit. The new branch appears only when both proofs pass.

## Work locally

Scaffold against a local checkout whose `origin` identifies the allowlisted repository:

```bash
npm run snippets:add -- \
  --source apps/app/src/pack/examples/sv-helm/validator-values.yaml \
  --local-checkout ../splice \
  --marker SWEEP
```

This prints a `local://canton-network/splice/...` ref. Paste it inside the release block and preview it with:

```bash
npm run snippets:preview -- \
  --page docs-main/global-synchronizer/deployment/validator.source.mdx \
  --candidate \
  --source-dir canton-network/splice=../splice
```

Once the upstream PR exists, convert the local refs in that already-conditioned block:

```bash
npm run snippets:resolve-local -- \
  --page docs-main/global-synchronizer/deployment/validator.source.mdx \
  --pull-request 6123
```

Validation rejects a committed `local://` ref with the page and line number plus this remediation. `resolve-local` writes nothing unless the resulting candidate ref is inside an `IfVersion` for the same repository and PR.

## Preview releases

Preview one release, repeated exact releases, an inclusive range of jointly published releases, or the versions currently deployed to all three networks:

```bash
npm run snippets:preview -- --page docs-main/path/validator.source.mdx --release 0.7.0
npm run snippets:preview -- --page docs-main/path/validator.source.mdx --release 0.6.14 --release 0.7.0
npm run snippets:preview -- --page docs-main/path/validator.source.mdx --releases 0.6.13..0.7.0
npm run snippets:preview -- --page docs-main/path/validator.source.mdx --deployed
```

Multiple targets render as tabs on one page. `--deployed` reads the checked-in version dashboard and labels the tabs `DevNet`, `TestNet`, and `MainNet` with their versions. `--candidate` adds a candidate tab using the PR heads already declared in the page.

## Generate and validate

Generate the Mintlify page and checked-in release evidence, then validate the authored contract and generated drift:

```bash
npm run snippets:generate -- --page docs-main/path/validator.source.mdx --deployed
npm run snippets:validate
npm run snippets:check -- --page docs-main/path/validator.source.mdx --deployed
```

The evidence records the PR/head or merge commit, release commit, source tag, artifact tag, publication result, ancestry result, and decision for every network/release condition. A page containing only immutable snippets needs no release selector:

```bash
npm run snippets:generate -- --page docs-main/path/example.source.mdx
```

## Legacy migration compatibility

The migration of existing manifest-backed snippets preserves old output while moving the complete source reference into the page. Old positional mappings can use an inclusive `lines="START..END"` selector. `normalize="baseline"` removes common indentation; `normalize="preserve"` retains it. These attributes exist only so current content can move without changing what readers see. New snippets must use complete files or named markers.

The two historical Splice KMS examples also declare their old URL substitution directly with paired `replaceFrom` and `replaceWith` attributes. There is no hidden repository-wide transform registry.

Each migrated page is checked in twice: the authored `*.source.mdx` and its generated `*.mdx`. Compilation caches repeated reads of the same immutable file, so a page with many snippets from one source fetches that source only once.

There are no move or delete commands. Move a source by editing its complete inline reference. Delete a snippet by deleting its declaration and related prose. Regenerate afterward; validation catches unresolved references and stale output.
