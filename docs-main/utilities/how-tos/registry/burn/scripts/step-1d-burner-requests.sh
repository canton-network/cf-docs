#!/usr/bin/env bash

## =================================================================================================
## Burner requests a burn of its holdings
## Step 1d: Execute the burn-request command
## Authorized by: Burner
## Script: step-1d-burner-requests.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

DATE_FORMAT='+%Y-%m-%dT%H:%M:%SZ'
NOW_ISO_TIMESTAMP=$(date -u "$DATE_FORMAT")
ONEHOUR_ISO_TIMESTAMP=$(date -u -d '+1 hour' "$DATE_FORMAT")

HOLDINGCIDS=$(cat "response-step-1b.json")

JSONCONTENT=$(cat "response-step-1c.json")
FACTORYID=$(echo $JSONCONTENT | jq .factoryId)
CHOICECONTEXTDATA=$(echo $JSONCONTENT | jq .choiceContext.choiceContextData)
DISCLOSEDCONTRACTS=$(echo $JSONCONTENT | jq .choiceContext.disclosedContracts)
DISCLOSEDCONTRACTS=$(echo $JSONCONTENT | jq '.choiceContext.disclosedContracts // [] | map(. + {"synchronizerId": ""})')

RESULT=$(
    curl -s \
    --url "${HTTP_JSON_API}/v2/commands/submit-and-wait-for-transaction" \
    --header "Authorization: Bearer ${BURNER_TOKEN}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
   "commands":{
        "commands":[
            {
                "ExerciseCommand":{
                    "templateId":"${ALLOCATIONFACTORY_TEMPLATE}",
                    "contractId":${FACTORYID},
                    "choice":"AllocationFactory_RequestBurn",
                    "choiceArgument":{
                        "expectedAdmin":"${ADMIN_PARTY_ID}",
                        "burn": {
                            "instrumentId": {
                              "admin": "${ADMIN_PARTY_ID}",
                              "id": "${ASSET_ID}"
                            },
                            "amount": "${ASSET_AMOUNT}",
                            "holder": "${BURNER_PARTY_ID}",
                            "reference": "${BURN_REF}",
                            "requestedAt": "${NOW_ISO_TIMESTAMP}",
                            "executeBefore": "${ONEHOUR_ISO_TIMESTAMP}",
                            "meta": {
                              "values": {}
                            }
                        },
                        "holdingCids":${HOLDINGCIDS},
                        "extraArgs":{
                            "context":${CHOICECONTEXTDATA},
                            "meta":{
                                "values":{
                                }
                            }
                        }
                    }
                }
            }
        ],
        "workflowId":"",
        "userId":"${BURNER_USER_ID}",
        "commandId":"$(uuidgen | tr -d '\n')",
        "deduplicationPeriod":{
            "DeduplicationDuration":{
                "value":{
                    "seconds":30,
                    "nanos":0
                }
            }
        },
        "actAs":[
            "${BURNER_PARTY_ID}"
        ],
        "readAs":[
        ],
        "submissionId":"$(uuidgen | tr -d '\n')",
        "disclosedContracts": ${DISCLOSEDCONTRACTS},
        "domainId":"",
        "packageIdSelectionPreference":[]
    }
}
EOF
)

echo "--- Command response ---"
echo $RESULT | jq

OUTPUTFILE="response-step-1d.json"
echo "$RESULT" > "$OUTPUTFILE"
