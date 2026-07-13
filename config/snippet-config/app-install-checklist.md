# CF Docs snippet sync — GitHub App install checklist

Use this checklist when setting up **cf-docs-snippet-reader** and **cf-docs-snippet-writer**.

App registration is done in the **GitHub web UI only**.

Related docs: [update-workflow-rev2.md](./update-workflow-rev2.md) · [source-repo-workflow-readme.md](./source-repo-workflow-readme.md)

---

## Prerequisites

- [ ] Org admin access on the org that **owns cf-docs** ([digital-asset/docs](https://github.com/digital-asset/docs))
- [ ] Permission to install third-party/org apps on each **source** repository.

---

## App 1: `cf-docs-snippet-reader`

### Create the app

**GitHub → Organization settings → Developer settings → GitHub Apps → New GitHub App**

| Field | Value |
|-------|--------|
| GitHub App name | `cf-docs-snippet-reader` |
| Description | Read GHA artifacts from snippet source repos for cf-docs |
| Homepage URL | cf-docs repository URL |
| Callback URL | *(leave empty)* |
| Webhook | **Disable** (uncheck Active) |
| Repository permissions → **Actions** | **Read-only** |
| Repository permissions → **Metadata** | Read-only *(automatic)* |
| Where can this GitHub App be installed? | Only on this account, or allowlist partner orgs |

- [ ] Click **Create GitHub App**
- [ ] Record **App ID**: `________________`
- [ ] **Generate a private key** → download `.pem` → store securely
- [ ] *(Optional)* Upload logo / set description for discoverability in org app requests

### Install reader app on source repositories

**GitHub App → Install App → Configure**

Install on **each repository** that publishes snippets (select repositories):

- [ ] [DACH-NY/canton](https://github.com/DACH-NY/canton)
- [ ] [canton-network/splice](https://github.com/canton-network/splice)
- [ ] [digital-asset/daml](https://github.com/digital-asset/daml)
- [ ] [digital-asset/cn-quickstart](https://github.com/digital-asset/cn-quickstart)
- [ ] [DACH-NY/daml-shell](https://github.com/DACH-NY/daml-shell)
- [ ] [digital-asset/dpm](https://github.com/digital-asset/dpm)
- [ ] [DACH-NY/scribe](https://github.com/DACH-NY/scribe)

**Do not** install the reader app on cf-docs.

---

## App 2: `cf-docs-snippet-writer`

### Create the app

**New GitHub App** (same org as above)

| Field | Value |
|-------|--------|
| GitHub App name | `cf-docs-snippet-writer` |
| Description | Dispatch snippet updates and open PRs on cf-docs |
| Homepage URL | cf-docs repository URL |
| Webhook | **Disable** |
| Repository permissions → **Contents** | **Read and write** |
| Repository permissions → **Pull requests** | **Read and write** |
| Repository permissions → **Metadata** | Read-only *(automatic)* |

- [ ] Click **Create GitHub App**
- [ ] Record **App ID**: `________________`
- [ ] **Generate a private key** → download `.pem` → store securely

### Install writer app on cf-docs only

- [ ] Install on [digital-asset/docs](https://github.com/digital-asset/docs)
- [ ] **Do not** install on source repositories

---

## Secrets: cf-docs repository

**Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|-------------|--------|
| `CF_DOCS_SNIPPET_READER_APP_ID` | Reader App ID |
| `CF_DOCS_SNIPPET_READER_PRIVATE_KEY` | Full PEM file contents (including `BEGIN` / `END` lines) |
| `CF_DOCS_SNIPPET_WRITER_APP_ID` | Writer App ID |
| `CF_DOCS_SNIPPET_WRITER_PRIVATE_KEY` | Full PEM file contents |

- [ ] All four secrets configured
- [ ] Verified secret names match [pull-external-snippets.yml](/.github/workflows/pull-external-snippets.yml)

Remove legacy PAT secrets after verification:

- [ ] `EXTERNAL_REPO_TOKEN` revoked *(after successful app test)*
- [ ] `DOCS_PR_TOKEN` revoked *(after successful app test)*

---

## Secrets: source repositories

Each repo that **dispatches** `update_snippets` needs writer app credentials.

**Prefer organization secrets** when repos share an org; use repository secrets for cross-org repos (e.g. Canton on `DACH-NY`).

| Secret name | Value |
|-------------|--------|
| `CF_DOCS_SNIPPET_WRITER_APP_ID` | Writer App ID (same as cf-docs) |
| `CF_DOCS_SNIPPET_WRITER_PRIVATE_KEY` | Writer PEM (same key) |

### Canton ([DACH-NY/canton](https://github.com/DACH-NY/canton))

CircleCI bridge — see [update-workflow-rev2.md § Canton](./update-workflow-rev2.md#canton-circleci--gha-bridge).

- [ ] Writer app secrets on Canton repo (or `DACH-NY` org secret)
- [ ] `CIRCLECI_API_TOKEN` on Canton GHA
- [ ] `MAIN_REPO_ORG` / `MAIN_REPO_NAME` repository variables
- [ ] `ENABLE_CFDOCS_SNIPPET_SYNC` = `true` when ready
- [ ] CircleCI context: `GITHUB_TOKEN` (`canton-machine` PAT) for CCI → Canton GHA dispatch
- [ ] CircleCI: `FAIL_ON_CF_DOCS_ERROR` **not set** during initial rollout *(optional strict mode later)*

Remove after verification:

- [ ] `MAIN_DOCS_REPO_TOKEN` revoked on Canton

### Splice ([canton-network/splice](https://github.com/canton-network/splice))

Standard GHA flow — see [update-workflow-rev2.md § Splice](./update-workflow-rev2.md#splice-gha-source) and [source-repo-workflow-readme.md](./source-repo-workflow-readme.md).

- [ ] Reader app installed on [canton-network/splice](https://github.com/canton-network/splice)
- [ ] Writer app secrets on splice repo (or `canton-network` org secret)
- [ ] Repository variables: `MAIN_REPO_ORG` = `digital-asset`, `MAIN_REPO_NAME` = `docs`
- [ ] `ENABLE_SYNC_PROCESS` = `true` when ready
- [ ] `.github/workflows/publish-cfdocs-snippets.yml` merged
- [ ] Extraction scripts present under `gha-scripts/cf-docs/` (`generateOutputDocs.js`, `exportConfig.json`)

### Other GHA source repos

Repeat reader install, writer secrets, and variables per repo. See [source repo tracker](./update-workflow-rev2.md#source-repo-installation) and [source-repo-workflow-readme.md](./source-repo-workflow-readme.md).

| Repository | Writer secrets | Variables |
|------------|----------------|-----------|
| [digital-asset/daml](https://github.com/digital-asset/daml) | org or repo | `MAIN_REPO_ORG`, `MAIN_REPO_NAME`, **`ENABLE_SYNC_PROCESS`** |
| [digital-asset/cn-quickstart](https://github.com/digital-asset/cn-quickstart) | org or repo | same |
| [DACH-NY/daml-shell](https://github.com/DACH-NY/daml-shell) | org or repo | same |
| [digital-asset/dpm](https://github.com/digital-asset/dpm) | org or repo | same |
| [DACH-NY/scribe](https://github.com/DACH-NY/scribe) | org or repo | same |

Set **`ENABLE_SYNC_PROCESS`** = `true` only when the publish workflow, extraction scripts, and app credentials are verified. While unset, the workflow may trigger on `main` but the publish job is skipped.

---

## Workflow PRs (merge after secrets exist)

| Order | Repository | Workflow file |
|-------|------------|---------------|
| 1 | [digital-asset/docs](https://github.com/digital-asset/docs) | `.github/workflows/pull-external-snippets.yml` |
| 2 | [DACH-NY/canton](https://github.com/DACH-NY/canton) | [publish-cfdocs-snippets-canton-bridge.yml](/scripts/templates/publish-cfdocs-snippets-canton-bridge.yml) → `.github/workflows/publish-cfdocs-snippets.yml` |
| 3 | Each GHA source | [publish-cfdocs-snippets.yml](/scripts/templates/publish-cfdocs-snippets.yml) → `.github/workflows/publish-cfdocs-snippets.yml` |

- [ ] cf-docs pull workflow merged
- [ ] Canton bridge workflow merged
- [ ] Source repo workflows updated

---

## Verification

### 1. Reader token (cf-docs)

- [ ] Run **Pull external Snippet updates** via `workflow_dispatch` with a known `artifact-id`, `run-id`, `repo-org`, `repo-name`, `repo-version` from a recent source-repo GHA run
- [ ] Confirm artifact downloads and files land under `docs-main/snippets/external/{repo}/{version}/`

### 2. Writer token (cf-docs PR)

- [ ] Same run creates or updates `external-snippet-update-{repo}-{version}` PR

### 3. Canton end-to-end

- [ ] Green `main` build: CircleCI `export_mintlify_snippets` completes (soft-fail OK if `FAIL_ON_CF_DOCS_ERROR` unset)
- [ ] Canton GHA **Publish CF Docs Snippets** runs
- [ ] cf-docs **Pull external Snippet updates** runs → PR updated

### 4. Splice end-to-end

- [ ] Push to `main` touching a snippet source path (or `workflow_dispatch`)
- [ ] [canton-network/splice](https://github.com/canton-network/splice) **Publish CF Docs Snippets** runs → artifact uploaded → cf-docs dispatch
- [ ] cf-docs PR updated under `docs-main/snippets/external/splice/main/`

### 5. Revoke PATs

- [ ] Remove `EXTERNAL_REPO_TOKEN`, `DOCS_PR_TOKEN`, `MAIN_DOCS_REPO_TOKEN` from all repos
- [ ] Update [source repo installation](./update-workflow-rev2.md#source-repo-installation) tracker

---

## Key rotation

When rotating a private key:

1. Generate new private key in GitHub App settings (old key remains valid until revoked)
2. Update all GitHub Secrets that reference the PEM
3. Run verification steps above
4. Revoke old private key in GitHub App settings

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `401` / `403` on `download-artifact` | Reader app installed on **source** repo; token minted with correct `owner` / `repositories` |
| `403` on `create-pull-request` | Writer app installed on **cf-docs**; PEM matches writer app |
| `403` on source → cf-docs dispatch | Writer secrets on source repo; `MAIN_REPO_ORG` / `MAIN_REPO_NAME` correct |
| Bridge workflow skipped | `ENABLE_CFDOCS_SNIPPET_SYNC` = `true` on Canton |
| GHA source workflow skipped | `ENABLE_SYNC_PROCESS` = `true` on source repo |
| CCI dispatch failed but job green | Expected when `FAIL_ON_CF_DOCS_ERROR` is unset |
| CCI dispatch failed and job red | Set `FAIL_ON_CF_DOCS_ERROR` only when snippet sync must block `main` |
