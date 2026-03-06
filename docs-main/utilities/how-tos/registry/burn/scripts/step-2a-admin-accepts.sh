#!/usr/bin/env bash

## =================================================================================================
## Admin accepts the burn request
## Step 2a: Obtains ledger end offset
## Authorized by: Admin
## Script: step-2a-admin-accepts.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

# Get offset from previous step
OFFSET=$(curl -s GET \
    --url "${HTTP_JSON_API}/v2/state/ledger-end" \
    --header "Accept: application/json" \
    --header "Authorization: Bearer ${ADMIN_PARTY_ID}")

echo "$OFFSET" | jq

OUTPUTFILE="response-step-2a.json"
echo "$OFFSET" > "$OUTPUTFILE"
