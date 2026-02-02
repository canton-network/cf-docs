#!/usr/bin/env bash

## =================================================================================================
## Sender offers a transfer
## Step 1d: Executes the transfer-offer command
## Authorized by: Sender
## Script: step-1d-sender-offers.sh
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

RESULT=$(
    curl -s \
    --url "${HTTP_JSON_API}/v2/commands/submit-and-wait-for-transaction" \
    --header "Authorization: Bearer ${SENDER_TOKEN}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
   "commands":{
        "commands":[
            {
                "ExerciseCommand":{
                    "templateId":"${TRANSFERFACTORY_INTERFACE}",
                    "contractId":${FACTORYID},
                    "choice":"TransferFactory_Transfer",
                    "choiceArgument":{
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
        "userId":"${SENDER_USER_ID}",
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
            "${SENDER_PARTY_ID}"
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
