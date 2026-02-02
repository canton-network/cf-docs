#!/usr/bin/env bash

## =================================================================================================
## Burner requests a burn of its holdings
## Step 1c: Gets choice context and disclosure for the burn-request command
## Authorized by: anyone
## Script: step-1c-burner-requests.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

DATE_FORMAT='+%Y-%m-%dT%H:%M:%SZ'
NOW_ISO_TIMESTAMP=$(date -u "$DATE_FORMAT")
ONEHOUR_ISO_TIMESTAMP=$(date -u -d '+1 hour' "$DATE_FORMAT")

HOLDINGCIDS=$(cat "response-step-1b.json")

RESULT=$(
    curl -s \
    --url "${BACKEND_API}/v0/registry/burn/v0/request" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
  "holder": "${BURNER_PARTY_ID}",
  "holdingContractIds":${HOLDINGCIDS},
  "instrumentId": {
    "admin": "${ADMIN_PARTY_ID}",
    "id": "${ASSET_ID}"
  }
}
EOF
)

echo "--- Endpoint response ---"
echo $RESULT | jq

OUTPUTFILE="response-step-1c.json"
echo "$RESULT" > "$OUTPUTFILE"
