#!/usr/bin/env bash

## =================================================================================================
## Minter requests a mint
## Step 1a: Gets choice context and disclosure for mint request
## Authorized by: Minter
## Script: step-1a-minter-requests.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

DATE_FORMAT='+%Y-%m-%dT%H:%M:%SZ'
NOW_ISO_TIMESTAMP=$(date -u "$DATE_FORMAT")
ONEHOUR_ISO_TIMESTAMP=$(date -u -d '+1 hour' "$DATE_FORMAT")

RESULT=$(
    curl -s \
    --url "${BACKEND_API}/v0/registry/mint/v0/request" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
  "holder": "${MINTER_PARTY_ID}",
  "instrumentId": {
    "admin": "${ADMIN_PARTY_ID}",
    "id": "${ASSET_ID}"
  }
}
EOF
)

echo "--- Endpoint response ---"
echo $RESULT | jq

OUTPUTFILE="response-step-1a.json"
echo "$RESULT" > "$OUTPUTFILE"
