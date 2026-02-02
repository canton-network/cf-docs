#!/usr/bin/env bash

## =================================================================================================
## Admin accepts the mint request
## Step 2c: Gets choice context and disclosure for the accept-mint-request command
## Authorized by: anyone
## Script: step-2c-admin-accepts.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

DATE_FORMAT='+%Y-%m-%dT%H:%M:%SZ'
NOW_ISO_TIMESTAMP=$(date -u "$DATE_FORMAT")
ONEHOUR_ISO_TIMESTAMP=$(date -u -d '+1 hour' "$DATE_FORMAT")

MINTREQUESTS=$(cat "response-step-2b.json")
MINTREQUEST_CID=$(echo "$MINTREQUESTS" | jq -r --arg MINT_REF "$MINT_REF" '[.[] | select(.contractEntry.JsActiveContract.createdEvent.createArgument.mint.reference == $MINT_REF)][0].contractEntry.JsActiveContract.createdEvent.contractId')

RESULT=$(
    curl -s \
    --url "${BACKEND_API}/v0/registry/mint/v0/request/${MINTREQUEST_CID}/choice-contexts/accept" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
   "meta":{

   },
   "excludeDebugFields": true
}
EOF
)

echo "--- Endpoint response ---"
echo $RESULT | jq

OUTPUTFILE="response-step-2c.json"
echo "$RESULT" > "$OUTPUTFILE"
