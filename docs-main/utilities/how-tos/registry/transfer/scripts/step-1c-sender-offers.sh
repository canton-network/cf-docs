#!/usr/bin/env bash

## =================================================================================================
## Sender offers a transfer
## Step 1c: Gets choice context and disclosure for the transfer-offer command
## Authorized by: anyone
## Script: step-1c-sender-offers.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

DATE_FORMAT='+%Y-%m-%dT%H:%M:%SZ'
NOW_ISO_TIMESTAMP=$(date -u "$DATE_FORMAT")
ONEHOUR_ISO_TIMESTAMP=$(date -u -d '+1 hour' "$DATE_FORMAT")

HOLDINGCIDS=$(cat "response-step-1b.json")

RESULT=$(
    curl -s \
    --url "${BACKEND_API}/v0/registrars/${ADMIN_PARTY_ID}/registry/transfer-instruction/v1/transfer-factory" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
   "choiceArguments":{
      "expectedAdmin":"${ADMIN_PARTY_ID}",
      "transfer":{
         "sender":"${SENDER_PARTY_ID}",
         "receiver":"${RECEIVER_PARTY_ID}",
         "amount":"${ASSET_AMOUNT}",
         "instrumentId":{
            "admin":"${ADMIN_PARTY_ID}",
            "id":"${ASSET_ID}"
         },
         "requestedAt":"${NOW_ISO_TIMESTAMP}",
         "executeBefore":"${ONEHOUR_ISO_TIMESTAMP}",
         "inputHoldingCids":${HOLDINGCIDS},
         "meta":{
            "values":{
               "splice.lfdecentralizedtrust.org/reason":""
            }
         }
      },
      "extraArgs":{
         "context":{
            "values":{

            }
         },
         "meta":{
            "values":{

            }
         }
      }
   },
   "excludeDebugFields":true
}
EOF
)

echo "--- Endpoint response ---"
echo $RESULT | jq

OUTPUTFILE="response-step-1c.json"
echo "$RESULT" > "$OUTPUTFILE"
