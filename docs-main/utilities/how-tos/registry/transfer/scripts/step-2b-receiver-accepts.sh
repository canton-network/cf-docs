#!/usr/bin/env bash

## =================================================================================================
## Receiver accepts offer
## Step 2b: Retrieves the transfer offer to accept
## Authorized by: Receiver
## Script: step-2b-receiver-accepts.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

JSONCONTENT=$(cat "response-step-2a.json")
OFFSET=$(echo "$JSONCONTENT" | jq -r ".offset")

RESULT=$(
    curl -s \
    --url "${HTTP_JSON_API}/v2/state/active-contracts" \
    --header "Authorization: Bearer ${RECEIVER_TOKEN}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
    "verbose": false,
    "activeAtOffset": "${OFFSET}",
    "filter": {
        "filtersByParty": {
            "${RECEIVER_PARTY_ID}": {
                "cumulative": [{
                    "identifierFilter": {
                        "InterfaceFilter": {
                            "value": {
                                "interfaceId":"$TRANSFER_INSTRUCTION_INTERFACE",
                                "includeInterfaceView": true,
                                "includeCreatedEventBlob": false
                            }
                        }
                    }
                }]
            }
        }
    }
}
EOF
)

echo "--- Transfer Offer for Sender ---"
echo "$RESULT" | jq

OUTPUTFILE="response-step-2b.json"
echo "$RESULT" > "$OUTPUTFILE"
