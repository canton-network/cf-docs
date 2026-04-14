# External repo snippet update flow 

# Tokens and variables/secrets configuration

## Target repository (this repo) configuration

On the target repository, the following repository environment **secrets** must be configured:
* `EXTERNAL_REPO_TOKEN` - token used to access the artifact of the external repository
* `DOCS_PR_TOKEN - token used to create the Pull Request on this repository


## Source repository configuration

On the source repository, the following secret must be configured:
* `MAIN_DOCS_REPO_TOKEN`

additionally, the following environment variables must be set:
* `MAIN_REPO_ORG` - `digital-asset`
* `MAIN_REPO_NAME` - `docs`
* `SOURCE_REPO_NAME` - `{SOURCE_REPOSITORY_NAME}`
* `SOURCE_REPO_ORG` - `{SOURCE_REPOSITORY_ORG}`
* `SOURCE_REPO_VERSION` - `main`

## Token permissions

The following token permission must be configured on these tokens:

**EXTERNAL_REPO_TOKEN**
repository scope: External repositories
* `hyperledger-labs/splice-wallet-kernel/`
* `DACH-NY/canton`
* `digital-asset/daml`
* `hyperledger-labs/splice`
* TODO: finalize list

permission scope:
* Actions: Read

**DOCS_PR_TOKEN**
repository scope: This repository (`digital-asset/docs`)
permission scope:
* Contents: Read and write
* Pull requests: Read and write

**MAIN_DOCS_REPO_TOKEN**
repository scope: This repository (`digital-asset/docs`)
permission scope:
* Contents: Read and write

Note: The `DOCS_PR_TOKEN` can also be used as `MAIN_DOCS_REPO_TOKEN`

# Workflow architecture

Changes in the external repository snippet source files are being extracted on the external repository, wrapped into an artifact and then being pulled in from this repository into the appropriate folder in the `snippets/external/` folder.


## Extract snippet files

In the external repository, three files control the extraction of snippets:
* [config/snippet-config/update-docs-snippets.yml](/config/snippet-config/update-docs-snippets.yml) - GitHub workflow file
* [config/snippet-config/splice-wallet-kernel-snippet-list-remote.json](/config/snippet-config/splice-wallet-kernel-snippet-list-remote.json) - The list defining the snippets to be extracted
* [scripts/helpers/generateOutputDocs.js](/scripts/helpers/generateOutputDocs.js) - Script that extracts the snippets defined in the snippet list.

The location of the script and config file might vary depending on the source repo file structure. In the splice-wallet-kernel repository, these are placed inside the `/docs/` folder:
* The snippet list json file is located at `/docs/config/exportConfig.json`
* The helper script is located at `/docs/scripts/generateOutputDocs.js`

The GitHub action file needs to be adjusted accordingly:

```
paths:
  - docs/wallet-integration-guide/examples/snippets/**
  - docs/wallet-integration-guide/examples/scripts/**
```
Line 9-11 with the paths to trigger the update workflow

```
run: node docs/scripts/generateOutputDocs.js
```
Line 21 with the path to the `generateOutputDocs.js` script

The snippet extraction script is then called from the GitHub action and extracts snippet files into a temp folder `docs-output`. The content of this folder (full extract) is then stored into the [GitHub artifact storage](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts). Afterwards, the `update_snippets` workflow is called on the main repository (this repo), which will pull the snippet files.

## Pulling snippet files

In this repository, the [pull-external-snippets](/.github/workflows/pull-external-snippets) workflow (dispatch name: `update_snippets`) is triggered with the following parameters:
* artifact-id: External Artifact Id
* run-id: Github Action Run Id
* repo-name: External repo name
* repo-org: External repo org
* repo-version: External repo version

It pulls the external artifact and places the files into `snippets/external/{repo_name}/{repo_version}`. Then, a PR is created (if there are any changed files) towards main on this repository. The PR title contains the repo name, version and the last commit hash (short) of the external repo. If another update is pushed on the external repository, the existing PR is being updated automatically.