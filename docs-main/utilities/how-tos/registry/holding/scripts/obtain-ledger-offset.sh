#!/usr/bin/env bash

# obtain-ledger-offset.sh - Obtains the ledger end offset

DATAFILE="source.sh"
source "$DATAFILE"

OFFSET=$(curl -s GET \
    --url "${HTTP_JSON_API}/v2/state/ledger-end" \
    --header "Accept: application/json" \
    --header "Authorization: Bearer ${USER_TOKEN}")

echo "$OFFSET" | jq

OUTPUTFILE="response-obtain-ledger-offset.json"
echo "$OFFSET" > "$OUTPUTFILE"