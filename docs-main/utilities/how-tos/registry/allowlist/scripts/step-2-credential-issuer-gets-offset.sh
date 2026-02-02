#!/usr/bin/env bash

## =================================================================================================
## How-to Tutorial: Manage allowlist-entry credentials
## Step 2: Credential issuer gets ledger offset
## Authorized by: credential issuer
## Script: step-2-credential-issuer-gets-offset.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

OFFSET=$(curl -s \
    --url "${HTTP_JSON_API}/v2/state/ledger-end" \
    --header "Accept: application/json" \
    --header "Authorization: Bearer ${CREDENTIAL_ISSUER_TOKEN}")

echo "$OFFSET" | jq

OUTPUTFILE="response-step-2.json"
echo "$OFFSET" > "$OUTPUTFILE"
