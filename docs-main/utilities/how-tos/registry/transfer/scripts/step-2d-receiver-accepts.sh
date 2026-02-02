#!/usr/bin/env bash

## =================================================================================================
## Receiver accepts offer
## Step 2d: Executes the accept transfer command
## Authorized by: Receiver
## Script: step-2d-receiver-accepts.sh
## =================================================================================================

DATAFILE="source.sh"
source "$DATAFILE"

INSTRUCTION=$(cat "response-step-2b.json")
INSTRUCTION_TEMPLATE=$(echo $INSTRUCTION | jq '.[] | .contractEntry.JsActiveContract.createdEvent.interfaceViews[0].interfaceId' | tr -d '"')
INSTRUCTION_CID=$(echo $INSTRUCTION | jq '.[] | .contractEntry.JsActiveContract.createdEvent.contractId')

JSONCONTENT=$(cat "response-step-2c.json")
CHOICECONTEXTDATA=$(echo $JSONCONTENT | jq .choiceContextData)
DISCLOSEDCONTRACTS=$(echo $JSONCONTENT | jq .disclosedContracts)

RESULT=$(
    curl -s \
    --url "${HTTP_JSON_API}/v2/commands/submit-and-wait-for-transaction" \
    --header "Authorization: Bearer ${RECEIVER_TOKEN}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
   "commands":{
        "commands":[
            {
                "ExerciseCommand":{
                    "templateId":"${INSTRUCTION_TEMPLATE}",
                    "contractId":${INSTRUCTION_CID},
                    "choice":"TransferInstruction_Accept",
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
        "userId":"${RECEIVER_USER_ID}",
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
            "${RECEIVER_PARTY_ID}"
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
