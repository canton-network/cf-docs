#!/usr/bin/env bash

## =================================================================================================
## How-to Tutorial: Manage allowlist-entry credentials
## Step 1: Credential issuer createss allowlist-entry `Utility.Credential.V0.Credential:Credential`s
## for multiple subjects in a single transaction.
## Authorized by: credential issuer
## Script: step-1-credential-issuer-creates-allowlist-entries.sh
## =================================================================================================

set -euo pipefail

DATAFILE="source.sh"
source "$DATAFILE"

# Validate inputs
if [[ -z "${CREDENTIAL_SUBJECT_PARTY_IDS:-}" ]]; then
    echo "Error: CREDENTIAL_SUBJECT_PARTY_IDS is not set in source.sh"
    exit 1
fi
if [[ -z "${CREDENTIAL_CLAIMS_JSON:-}" ]]; then
    echo "Error: CREDENTIAL_CLAIMS_JSON is not set in source.sh"
    exit 1
fi
echo "${CREDENTIAL_SUBJECT_PARTY_IDS}" | jq -e 'type == "array" and length > 0 and all(.[]; type == "string")' >/dev/null
echo "${CREDENTIAL_CLAIMS_JSON}" | jq -e 'type == "array" and length > 0 and all(.[]; has("property") and has("value"))' >/dev/null

# Random Credential ID prefix.
ID_PREFIX="allowlist-entry: $(od -An -N4 -tu4 < /dev/urandom | tr -d ' ')"

COMMANDS_JSON=$(jq -n \
    --arg templateId "${CREDENTIAL_TEMPLATE}" \
    --arg issuer "${CREDENTIAL_ISSUER_PARTY_ID}" \
    --arg description "${CREDENTIAL_DESCRIPTION}" \
    --arg holder "${CREDENTIAL_ISSUER_PARTY_ID}" \
    --arg idPrefix "${ID_PREFIX}-" \
    --argjson subjects "${CREDENTIAL_SUBJECT_PARTY_IDS}" \
    --argjson claimPairs "${CREDENTIAL_CLAIMS_JSON}" \
    '[
        ($subjects | to_entries[]) as $entry
        | ($entry.key + 1) as $n
        | ($entry.value) as $subjectParty
        | {
                CreateCommand: {
                    templateId: $templateId,
                    createArguments: {
                        issuer: $issuer,
                        holder: $holder,
                        id: ($idPrefix + ($n | tostring)),
                        description: $description,
                        validFrom: null,
                        validUntil: null,
                        claims: (
                          $claimPairs
                          | map({subject: $subjectParty, property: .property, value: .value})
                        ),
                        observers: { map: [] }
                    }
                }
            }
    ]')

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

echo "--- Command response ---"
echo "$RESULT" | jq

OUTPUTFILE="response-step-1.json"
echo "$RESULT" > "$OUTPUTFILE"
