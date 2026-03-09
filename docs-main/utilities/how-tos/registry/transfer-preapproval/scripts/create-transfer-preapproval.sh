#!/usr/bin/env bash

## =================================================================================================
## How-to Tutorial: Create transfer preapproval
## Authorized by: receiver
## Script: create-transfer-preapproval.sh
## =================================================================================================

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/source.sh"

OUTPUT_DIR="${SCRIPT_DIR}/../response"
mkdir -p "$OUTPUT_DIR"

# Validate inputs
if [[ -z "${HTTP_JSON_API:-}" ]]; then
    echo "Error: HTTP_JSON_API is not set in source.sh"
    exit 1
fi
if [[ -z "${TRANSFER_PREAPPROVAL_TEMPLATE:-}" ]]; then
    echo "Error: TRANSFER_PREAPPROVAL_TEMPLATE is not set in source.sh"
    exit 1
fi
if [[ -z "${OPERATOR_PARTY_ID:-}" ]]; then
    echo "Error: OPERATOR_PARTY_ID is not set in source.sh"
    exit 1
fi
if [[ -z "${INSTRUMENT_ADMIN_PARTY_ID:-}" ]]; then
    echo "Error: INSTRUMENT_ADMIN_PARTY_ID is not set in source.sh"
    exit 1
fi
if [[ -z "${RECEIVER_TOKEN:-}" || -z "${RECEIVER_USER_ID:-}" || -z "${RECEIVER_PARTY_ID:-}" ]]; then
    echo "Error: RECEIVER_TOKEN/RECEIVER_USER_ID/RECEIVER_PARTY_ID must be set in source.sh"
    exit 1
fi
if [[ -z "${INSTRUMENT_IDS:-}" ]]; then
    echo "Error: INSTRUMENT_IDS is not set in source.sh"
    exit 1
fi
echo "${INSTRUMENT_IDS}" | jq -e 'type == "array" and all(.[]; type == "string")' >/dev/null

COMMANDS_JSON=$(jq -n \
    --arg templateId "${TRANSFER_PREAPPROVAL_TEMPLATE}" \
    --arg operator "${OPERATOR_PARTY_ID}" \
    --arg receiver "${RECEIVER_PARTY_ID}" \
    --arg instrumentAdmin "${INSTRUMENT_ADMIN_PARTY_ID}" \
    --argjson instrumentIds "${INSTRUMENT_IDS}" \
    '[
        {
            CreateCommand: {
                templateId: $templateId,
                createArguments: {
                    operator: $operator,
                    receiver: $receiver,
                    instrumentAdmin: $instrumentAdmin,
                    instrumentAllowances: ($instrumentIds | map({id: .}))
                }
            }
        }
    ]')

RESULT=$(
    curl -s \
        --url "${HTTP_JSON_API}/v2/commands/submit-and-wait-for-transaction" \
        --header "Authorization: Bearer ${RECEIVER_TOKEN}" \
        --header "Content-Type: application/json" \
        --request POST \
        --data @- <<EOF
{
    "commands": {
        "commands": ${COMMANDS_JSON},
        "workflowId": "",
        "userId": "${RECEIVER_USER_ID}",
        "commandId": "$(uuidgen | tr -d '\n')",
        "deduplicationPeriod": {
            "DeduplicationDuration": {
                "value": { "seconds": 30, "nanos": 0 }
            }
        },
        "actAs": [
            "${RECEIVER_PARTY_ID}"
        ],
        "readAs": [],
        "submissionId": "$(uuidgen | tr -d '\n')",
        "disclosedContracts": [],
        "domainId": "",
        "packageIdSelectionPreference": []
    }
}
EOF
)

echo "--- Command response ---"
echo "$RESULT" | jq

OUTPUTFILE="response-step-1.json"
echo "$RESULT" > "$OUTPUTFILE"
