#!/usr/bin/env bash

## =================================================================================================
## How-to Tutorial: Manage allowlist-entry credentials
## Step 3: Credential issuer retrieve active `Utility.Credential.V0.Credential:Credential` contracts
## issued for itself, filtered by expected claim property/value pairs.
## Authorized by: credential issuer
## Script: step-3-credential-issuer-retrieves-issued-credentials.sh
## =================================================================================================

set -euo pipefail

DATAFILE="source.sh"
source "$DATAFILE"

# Validate expected claim pairs config (property/value)
if [[ -z "${CREDENTIAL_CLAIMS_JSON:-}" ]]; then
  echo "Error: CREDENTIAL_CLAIMS_JSON is not set in source.sh" >&2
  exit 1
fi

echo "${CREDENTIAL_CLAIMS_JSON}" | jq -e 'type == "array" and all(.[]; (has("property") and has("value")))' >/dev/null

# Get offset from previous step
if [[ -f "response-step-2.json" ]]; then
  JSONCONTENT=$(cat "response-step-2.json")
  OFFSET=$(echo "$JSONCONTENT" | jq -r ".offset")
else
  echo "Error: response-step-2.json not found"
  exit 1
fi

RESULT=$(curl -s \
    --url "${HTTP_JSON_API}/v2/state/active-contracts" \
    --header "Authorization: Bearer ${CREDENTIAL_ISSUER_TOKEN}" \
    --header "Content-Type: application/json" \
    --request POST \
    --data @- <<EOF
{
  "verbose": false,
  "activeAtOffset": "${OFFSET}",
  "filter": {
    "filtersByParty": {
      "${CREDENTIAL_ISSUER_PARTY_ID}": {
        "cumulative": [
          {
            "identifierFilter": {
              "TemplateFilter": {
                "value": {
                  "templateId": "${CREDENTIAL_TEMPLATE}",
                  "includeCreatedEventBlob": false
                }
              }
            }
          }
        ]
      }
    }
  }
}
EOF
)

# Keep only credentials whose createArgument.issuer matches CREDENTIAL_ISSUER_PARTY_ID and whose
# claim property/value pairs match the configured CREDENTIAL_CLAIMS_JSON pairs (ignoring subject).
FILTERED=$(echo "$RESULT" | jq \
  --arg CREDENTIAL_ISSUER_PARTY_ID "$CREDENTIAL_ISSUER_PARTY_ID" \
  --argjson expectedClaimPairs "${CREDENTIAL_CLAIMS_JSON}" \
  '[
    def normalizePairs($xs): ($xs | map({property: .property, value: .value}) | unique);
    def matchesPairsExactly($claims; $expected):
      (normalizePairs($expected)) as $e
      | (normalizePairs($claims)) as $a
      | ($a == $e);

    .[]
    | .contractEntry.JsActiveContract.createdEvent
    | {
        contractId: .contractId,
        createdAt: .createdAt,
        id: .createArgument.id,
        issuer: .createArgument.issuer,
        holder: .createArgument.holder,
        description: .createArgument.description,
        validFrom: .createArgument.validFrom,
        validUntil: .createArgument.validUntil,
        claims: .createArgument.claims
      }
    | select(.issuer == $CREDENTIAL_ISSUER_PARTY_ID)
    | select(matchesPairsExactly(.claims; $expectedClaimPairs))
  ]'
)

COUNT=$(echo "$FILTERED" | jq 'length')

echo "--- Issued credentials of ${CREDENTIAL_ISSUER_PARTY_ID} as of offset ${OFFSET} (count=${COUNT}) ---"
echo "$FILTERED" | jq

OUTPUTFILE="response-step-3.json"
echo "$FILTERED" > "$OUTPUTFILE"
