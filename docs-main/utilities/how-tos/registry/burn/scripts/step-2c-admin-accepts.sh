#!/usr/bin/env bash

## =================================================================================================
## Admin accepts the burn request
## Step 2c: Gets choice context and disclosure for the accept-burn-request command
## Authorized by: anyone
## Script: step-2c-admin-accepts.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

DATE_FORMAT='+%Y-%m-%dT%H:%M:%SZ'
NOW_ISO_TIMESTAMP=$(date -u "$DATE_FORMAT")
ONEHOUR_ISO_TIMESTAMP=$(date -u -d '+1 hour' "$DATE_FORMAT")

BURNREQUESTS=$(cat "response-step-2b.json")
BURNREQUEST_CID=$(echo "$BURNREQUESTS" | jq -r --arg BURN_REF "$BURN_REF" '[.[] | select(.contractEntry.JsActiveContract.createdEvent.createArgument.burn.reference == $BURN_REF)][0].contractEntry.JsActiveContract.createdEvent.contractId')

RESULT=$(
    curl -s \
    --url "${BACKEND_API}/v0/registry/burn/v0/request/${BURNREQUEST_CID}/choice-contexts/accept" \
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
