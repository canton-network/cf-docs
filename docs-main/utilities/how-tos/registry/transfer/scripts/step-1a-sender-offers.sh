#!/usr/bin/env bash

## =================================================================================================
## Sender offers a transfer
## Step 1a: Obtains ledger end offset
## Authorized by: Sender
## Script: step-1a-sender-offers.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

OFFSET=$(curl -s GET \
    --url "${HTTP_JSON_API}/v2/state/ledger-end" \
    --header "Accept: application/json" \
    --header "Authorization: Bearer ${SENDER_TOKEN}")

echo "$OFFSET" | jq

OUTPUTFILE="response-step-1a.json"
echo "$OFFSET" > "$OUTPUTFILE"
