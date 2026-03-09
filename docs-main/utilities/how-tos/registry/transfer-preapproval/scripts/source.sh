#!/usr/bin/env bash

## =================================================================================================
## Purpose: Configurations for this example, amend variables as needed.
## Script: source.sh
## =================================================================================================

# Receiver details
RECEIVER_TOKEN="<PASTE_JWT_TOKEN_HERE>"
RECEIVER_PARTY_ID="holder::1220e71be62943820d0f7ecc365fc498adcd25e1b1fd165f0ae9b65c343230f93579"
RECEIVER_USER_ID="holder"

# Operator details
OPERATOR_PARTY_ID="operator::1220ae8c93e1f1263d0366cbc4c2a2fe587b5227e929ddd76528380c59deb58ada8f"
# You can retrieve the operator party ID from `http://<host>/api/utilities/v0/operator`, e.g.
# - Local:  `curl http://localhost:8080/api/utilities/v0/operator`
# - DevNet: `curl https://api.utilities.digitalasset-dev.com/api/utilities/v0/operator`

# Instrument admin (or registrar) details whose instruments are being preapproved.
INSTRUMENT_ADMIN_PARTY_ID="registrar::1220e71be62943820d0f7ecc365fc498adcd25e1b1fd165f0ae9b65c343230f93579"

# Instrument ids to preapprove (an empty list means all instruments are preapproved)
INSTRUMENT_IDS='[
	"INST"
]'

# JSON API endpoint
# Example (local): HTTP_JSON_API="http://localhost:8001/api/json-api"
# Example (remote): HTTP_JSON_API="https://<your-host>/api/json-api"
HTTP_JSON_API="http://localhost:8001/api/json-api"

# Daml template IDs (package-name qualified)
TRANSFER_PREAPPROVAL_TEMPLATE="#utility-registry-app-v0:Utility.Registry.App.V0.Model.TransferPreapproval:TransferPreapproval"
