#!/usr/bin/env bash

## =================================================================================================
## Receiver accepts offer
## Step 2a: Obtains ledger end offset
## Authorized by: Receiver
## Script: step-2a-receiver-accepts.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

# obtain ledger end
OFFSET=$(curl -s GET \
    --url "${HTTP_JSON_API}/v2/state/ledger-end" \
    --header "Accept: application/json" \
    --header "Authorization: Bearer ${RECEIVER_TOKEN}")

echo "$OFFSET" | jq

OUTPUTFILE="response-step-2a.json"
echo "$OFFSET" > "$OUTPUTFILE"
