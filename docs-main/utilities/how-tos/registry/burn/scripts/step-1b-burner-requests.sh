#!/usr/bin/env bash

## =================================================================================================
## Burner requests a burn of its holdings
## Step 1b: Retrieve the burner's holdings as of the offset from step 1a to use for the burn request
## Authorized by: Burner
## Script: step-1b-burner-requests.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

# Get offset from previous step
if [[ -f "response-step-1a.json" ]]; then
  JSONCONTENT=$(cat "response-step-1a.json")
  OFFSET=$(echo "$JSONCONTENT" | jq -r ".offset")
else
  echo "Error: response-step-1a.json not found"
  exit 1
fi

RESULT=$(
    curl -s \
    --url "${HTTP_JSON_API}/v2/state/active-contracts" \
    --header "Authorization: Bearer ${BURNER_TOKEN}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
    "verbose": false,
    "activeAtOffset": "${OFFSET}",
    "filter": {
        "filtersByParty": {
            "${BURNER_PARTY_ID}": {
                "cumulative": [{
                    "identifierFilter": {
                        "InterfaceFilter": {
                            "value": {
                                "interfaceId":"$HOLDING_INTERFACE",
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

# Filter holdings for a specific holder, instrument ID, admin and extract contractId
HOLDINGCIDS=$(echo "$RESULT" | jq \
  --arg BURNER_PARTY_ID "$BURNER_PARTY_ID" \
  --arg ASSET_ID "$ASSET_ID" \
  --arg ADMIN_PARTY_ID "$ADMIN_PARTY_ID" \
  '[
    .[] as $c
    | $c.contractEntry.JsActiveContract.createdEvent.interfaceViews[]
    | select(
        .viewValue.owner == $BURNER_PARTY_ID and
        .viewValue.instrumentId.id == $ASSET_ID and
        .viewValue.instrumentId.admin == $ADMIN_PARTY_ID
    )
    | $c.contractEntry.JsActiveContract.createdEvent.contractId
  ]'
)

echo "--- Holdings of burner (${BURNER_USER_ID}) as of offset ${OFFSET} ---"
echo "$HOLDINGCIDS" | jq

OUTPUTFILE="response-step-1b.json"
echo "$HOLDINGCIDS" > "$OUTPUTFILE"