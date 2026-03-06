#!/usr/bin/env bash

## =================================================================================================
## Burner requests a burn of its holdings
## Step 1a: Retrieves the current ledger end offset from the ledger
## Authorized by: Burner
## Script: step-1a-burner-requests.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

OFFSET=$(curl -s GET \
    --url "${HTTP_JSON_API}/v2/state/ledger-end" \
    --header "Accept: application/json" \
    --header "Authorization: Bearer ${BURNER_TOKEN}")

echo "$OFFSET" | jq

OUTPUTFILE="response-step-1a.json"
echo "$OFFSET" > "$OUTPUTFILE"
