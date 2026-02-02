#!/usr/bin/env bash

## =================================================================================================
## Admin accepts the burn request
## Step 2d: Executes the accept-burn-request command
## Authorized by: Admin
## Script: step-2d-admin-accepts.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

BURNREQUESTS=$(cat "response-step-2b.json")
BURNREQUEST=$(echo "$BURNREQUESTS" | jq -r --arg BURN_REF "$BURN_REF" '[.[] | select(.contractEntry.JsActiveContract.createdEvent.createArgument.burn.reference == $BURN_REF)][0]')
BURNREQUEST_CID=$(echo "$BURNREQUEST" | jq -r .contractEntry.JsActiveContract.createdEvent.contractId)
BURNREQUEST_TEMPLATE=$(echo "$BURNREQUEST" | jq -r .contractEntry.JsActiveContract.createdEvent.templateId)

JSONCONTENT=$(cat "response-step-2c.json")
CHOICECONTEXTDATA=$(echo $JSONCONTENT | jq .choiceContextData)
DISCLOSEDCONTRACTS=$(echo $JSONCONTENT | jq .disclosedContracts)
DISCLOSEDCONTRACTS=$(echo $JSONCONTENT | jq '.choiceContext.disclosedContracts // [] | map(. + {"synchronizerId": ""})')

RESULT=$(
    curl -s \
    --url "${HTTP_JSON_API}/v2/commands/submit-and-wait-for-transaction" \
    --header "Authorization: Bearer ${ADMIN_TOKEN}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
   "commands":{
        "commands":[
            {
                "ExerciseCommand":{
                    "templateId":"${BURNREQUEST_TEMPLATE}",
                    "contractId":"${BURNREQUEST_CID}",
                    "choice":"BurnRequest_Accept",
                    "choiceArgument":{
                        "extraArgs": {
                            "context": $CHOICECONTEXTDATA,
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
        "userId":"${ADMIN_USER_ID}",
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
            "${ADMIN_PARTY_ID}"
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

OUTPUTFILE="response-step-2d.json"
echo "$RESULT" > "$OUTPUTFILE"
