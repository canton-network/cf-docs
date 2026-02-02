#!/usr/bin/env bash

## =================================================================================================
## Purpose: Retrieves all templates for a specific user (limited to first RESULT_LIMIT results)
## Authorized by: User
## Script: retrieve-all.sh
## =================================================================================================

RESULT_LIMIT=3

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
            "${USER_PARTY_ID}": {}
        }
    }
}
EOF
)

LIMITED_RESULT=$(echo "$RESULT" | jq ".[0:${RESULT_LIMIT}]")

echo "--- First ${RESULT_LIMIT} templates of ${USER_PARTY_ID} as of offset ${OFFSET} ---"
echo "$LIMITED_RESULT"

OUTPUTFILE="response-retrieve-all.json"
echo "$LIMITED_RESULT" > "$OUTPUTFILE"
