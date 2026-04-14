# External repo snippet update flow 

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

### Token permissions

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

## Source repository configuration

**MAIN_DOCS_REPO_TOKEN**
repository scope: This repository (`digital-asset/docs`)
permission scope:
* Contents: Read and write

Note: The `DOCS_PR_TOKEN` can also be used as `MAIN_DOCS_REPO_TOKEN`
