#!/usr/bin/env bash

## =================================================================================================
## Purpose: Retrieves holdings of the user for a specific instrument and minimum amount
## Authorized by: User
## Script: retrieve-holdings.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

# Get offset from previous step
if [[ -f "response-obtain-ledger-offset.json" ]]; then
  JSONCONTENT=$(cat "response-obtain-ledger-offset.json")
  OFFSET=$(echo "$JSONCONTENT" | jq -r ".offset")
else
  echo "Error: response-obtain-ledger-offset.json not found"
  exit 1
fi

RESULT=$(curl -s \
    --url "${HTTP_JSON_API}/v2/state/active-contracts" \
    --header "Authorization: Bearer ${USER_TOKEN}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
    "verbose": false,
    "activeAtOffset": "${OFFSET}",
    "filter": {
        "filtersByParty": {
            "${USER_PARTY_ID}": {
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

# Filter holdings for a specific holder, instrument ID, admin, and minimum amount
FILTERED=$(echo "$RESULT" | jq \
  --arg USER_PARTY_ID "$USER_PARTY_ID" \
  --arg INSTRUMENT_ID "$INSTRUMENT_ID" \
  --arg ADMIN_PARTY_ID "$ADMIN_PARTY_ID" \
  --arg MIN_AMOUNT "$MIN_AMOUNT" \
  '[
    .[]
    | .contractEntry.JsActiveContract.createdEvent.interfaceViews[]
    | select(
        .viewValue.owner == $USER_PARTY_ID and
        .viewValue.instrumentId.id == $INSTRUMENT_ID and
        .viewValue.instrumentId.admin == $ADMIN_PARTY_ID and
        (.viewValue.amount | tonumber) > ($MIN_AMOUNT | tonumber)
    )
  ]'
)

echo "--- All interface holdings of ${USER_PARTY_ID} with amount>=${MIN_AMOUNT} as of offset ${OFFSET} ---"
echo "$FILTERED" | jq

OUTPUTFILE="response-retrieve-holdings.json"
echo "$FILTERED" > "$OUTPUTFILE"
