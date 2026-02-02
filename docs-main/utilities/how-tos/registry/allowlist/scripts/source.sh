#!/usr/bin/env bash

## =================================================================================================
## Purpose: Configurations for this example, amend variables as needed.
## Script: source.sh
## =================================================================================================

# Credential issuer details
CREDENTIAL_ISSUER_TOKEN="eyJhbGciOiJIUzI1NiJ9.eyJzY29wZSI6ImRhbWxfbGVkZ2VyX2FwaSIsImlhdCI6MTc2OTAxMTAzNSwiYXVkIjoiaHR0cHM6Ly91dGlsaXR5LmNhbnRvbi5uZXR3b3JrIiwic3ViIjoicmVnaXN0cmFyIn0.mm8wFTWR7y3DRcLC9xU1t9CUcsGStwf6mpBtuSvbvQA"
CREDENTIAL_ISSUER_PARTY_ID="registrar::12206746c7f1cdbde4c01cf2e83d45d1a25b34293e0ad07056547a5ce25074a7b30b"
CREDENTIAL_ISSUER_USER_ID="registrar"

# Subjects to create an allowlist-entry credential for.
CREDENTIAL_SUBJECT_PARTY_IDS='[
	"holder1::12206746c7f1cdbde4c01cf2e83d45d1a25b34293e0ad07056547a5ce25074a7b30b",
	"holder2::12206746c7f1cdbde4c01cf2e83d45d1a25b34293e0ad07056547a5ce25074a7b30b",
  "holder3::12206746c7f1cdbde4c01cf2e83d45d1a25b34293e0ad07056547a5ce25074a7b30b"
]'

# Description used for all created credentials
CREDENTIAL_DESCRIPTION="Allowlist-Entry Credential"

# Claims to attach to each created credential (JSON list).
# The scripts will set the `subject` field of each claim to the current subject party.
CREDENTIAL_CLAIMS_JSON='[
	{"property":"IsHolderOf","value":"INST1"},
	{"property":"IsHolderOf","value":"INST2"}
]'

# JSON API endpoint
# Example (local): HTTP_JSON_API="http://localhost:8001/api/json-api"
# Example (remote): HTTP_JSON_API="https://<your-host>/api/json-api"
HTTP_JSON_API="http://localhost:8001/api/json-api"

# Daml template IDs (package-name qualified)
CREDENTIAL_TEMPLATE="#utility-credential-v0:Utility.Credential.V0.Credential:Credential"
