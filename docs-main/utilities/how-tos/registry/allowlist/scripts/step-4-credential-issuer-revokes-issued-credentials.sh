#!/usr/bin/env bash

## =================================================================================================
## How-to Tutorial: Manage allowlist-entry credentials
## Step 4: Credential issuer revokes the active `Utility.Credential.V0.Credential:Credential`s
## contracts returned by step 3
## Authorized by: credential issuer
## Script: step-4-credential-issuer-revokes-issued-credentials.sh
## =================================================================================================

set -euo pipefail

DATAFILE="source.sh"
source "$DATAFILE"

CONTRACTS_FILE="response-step-3.json"

if [[ ! -f "$CONTRACTS_FILE" ]]; then
  echo "Error: ${CONTRACTS_FILE} not found. Run step 3 first." >&2
  exit 1
fi

# Extract contractIds from step 3 output.
CONTRACT_IDS_JSON=$(jq -c '[.[].contractId] | map(select(type == "string" and length > 0))' "$CONTRACTS_FILE")
COUNT=$(echo "$CONTRACT_IDS_JSON" | jq 'length')

if [[ "$COUNT" -eq 0 ]]; then
  echo "No contractIds found in ${CONTRACTS_FILE}. Nothing to archive." >&2
  echo "[]" > "response-step-4.json"
  exit 0
fi

COMMANDS_JSON=$(jq -n \
  --arg templateId "${CREDENTIAL_TEMPLATE}" \
  --argjson contractIds "${CONTRACT_IDS_JSON}" \
  '[
    $contractIds[]
    | {
        ExerciseCommand: {
          templateId: $templateId,
          contractId: .,
          choice: "Archive",
          choiceArgument: {}
        }
      }
  ]'
)

RESULT=$(
  curl -s \
    --url "${HTTP_JSON_API}/v2/commands/submit-and-wait-for-transaction" \
    --header "Authorization: Bearer ${CREDENTIAL_ISSUER_TOKEN}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
  "commands": {
    "commands": ${COMMANDS_JSON},
    "workflowId": "",
    "userId": "${CREDENTIAL_ISSUER_USER_ID}",
    "commandId": "$(uuidgen | tr -d '\n')",
    "deduplicationPeriod": {
      "DeduplicationDuration": {
        "value": { "seconds": 30, "nanos": 0 }
      }
    },
    "actAs": [
      "${CREDENTIAL_ISSUER_PARTY_ID}"
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

echo "--- Command response (archived count=${COUNT}) ---"
echo "$RESULT" | jq

OUTPUTFILE="response-step-4.json"
echo "$RESULT" > "$OUTPUTFILE"
