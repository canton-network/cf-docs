#!/usr/bin/env bash

## =================================================================================================
## Admin accepts the burn request
## Step 2b: Retrieves the burn request to accept
## Authorized by: Admin
## Script: step-2b-admin-accepts.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

JSONCONTENT=$(cat "response-step-2a.json")
OFFSET=$(echo "$JSONCONTENT" | jq -r ".offset")

RESULT=$(
    curl -s \
    --url "${HTTP_JSON_API}/v2/state/active-contracts" \
    --header "Authorization: Bearer ${ADMIN_TOKEN}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
    "verbose": false,
    "activeAtOffset": "${OFFSET}",
    "filter": {
        "filtersByParty": {
            "${ADMIN_PARTY_ID}": {
                "cumulative": [{
                    "identifierFilter": {
                        "TemplateFilter": {
                            "value": {
                                "templateId":"${BURNREQUEST_TEMPLATE}",
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

echo "--- Burn Request ---"
echo "$RESULT" | jq

OUTPUTFILE="response-step-2b.json"
echo "$RESULT" > "$OUTPUTFILE"
