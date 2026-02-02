#!/usr/bin/env bash

## =================================================================================================
## Minter requests a mint
## Step 1b: Executes the mint request command
## Authorized by: Minter
## Script: step-1b-minter-requests.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

DATE_FORMAT='+%Y-%m-%dT%H:%M:%SZ'
NOW_ISO_TIMESTAMP=$(date -u "$DATE_FORMAT")
ONEHOUR_ISO_TIMESTAMP=$(date -u -d '+1 hour' "$DATE_FORMAT")

JSONCONTENT=$(cat "response-step-1a.json")
FACTORYID=$(echo $JSONCONTENT | jq .factoryId)
CHOICECONTEXTDATA=$(echo $JSONCONTENT | jq .choiceContext.choiceContextData)
DISCLOSEDCONTRACTS=$(echo $JSONCONTENT | jq .choiceContext.disclosedContracts)
DISCLOSEDCONTRACTS=$(echo $JSONCONTENT | jq '.choiceContext.disclosedContracts // [] | map(. + {"synchronizerId": ""})')

RESULT=$(
    curl -s \
    --url "${HTTP_JSON_API}/v2/commands/submit-and-wait-for-transaction" \
    --header "Authorization: Bearer ${MINTER_TOKEN}" \
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
                    "choice":"AllocationFactory_RequestMint",
                    "choiceArgument":{
                        "expectedAdmin":"${ADMIN_PARTY_ID}",
                        "mint": {
                            "instrumentId": {
                              "admin": "${ADMIN_PARTY_ID}",
                              "id": "${ASSET_ID}"
                            },
                            "amount": "${ASSET_AMOUNT}",
                            "holder": "${MINTER_PARTY_ID}",
                            "reference": "${MINT_REF}",
                            "requestedAt": "${NOW_ISO_TIMESTAMP}",
                            "executeBefore": "${ONEHOUR_ISO_TIMESTAMP}",
                            "meta": {
                              "values": {}
                            }
                        },
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
        "userId":"${MINTER_USER_ID}",
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
            "${MINTER_PARTY_ID}"
        ],
        "readAs":[
        ],
        "submissionId":"$(uuidgen | tr -d '\n')",
        "disclosedContracts": ${DISCLOSEDCONTRACTS},
        "domainId":"",
        "packageIdSelectionPreference":[
        ]
    }
}
EOF
)

echo "--- Command response ---"
echo $RESULT | jq

OUTPUTFILE="response-step-1b.json"
echo "$RESULT" > "$OUTPUTFILE"
