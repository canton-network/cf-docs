#!/usr/bin/env bash

## =================================================================================================
## Purpose: Configurations for this example, amend variables as needed.
## Script: source.sh
## =================================================================================================

# Receiver's details
MINTER_TOKEN="<PASTE_JWT_TOKEN_HERE>"
MINTER_PARTY_ID="issuer::1220d301ababbed7bc8d6f6a80ce16f33933a7274a3013241b7fb373ca7e4f0d6567"
MINTER_USER_ID="issuer"

# Admin/Registrar details
ADMIN_TOKEN="<PASTE_JWT_TOKEN_HERE>"
ADMIN_PARTY_ID="registrar::1220d301ababbed7bc8d6f6a80ce16f33933a7274a3013241b7fb373ca7e4f0d6567"
ADMIN_USER_ID="registrar"

# Unique reference for the action
MINT_REF="mint-ref-002"

# Update your asset and amount to be transferred
ASSET_ID="INST"
ASSET_AMOUNT="5.0"

# Endpoints (pick one)
# - Remote: BACKEND_API="https://<your-host>/api/utilities" HTTP_JSON_API="https://<your-host>/api/json-api"
# - DevNet: BACKEND_API="https://api.utilities.digitalasset-dev.com/api/utilities" HTTP_JSON_API="https://utility.utility.cnu.devnet.da-int.net/api/json-api"
# - Local:  BACKEND_API="http://localhost:8080/api/utilities" HTTP_JSON_API="http://localhost:8001/api/json-api"
BACKEND_API="http://localhost:8080/api/utilities"
HTTP_JSON_API="http://localhost:8001/api/json-api"

# Token standard holding interface, may change when new versions of splice exists
# TRANSFERFACTORY_INTERFACE="55ba4deb0ad4662c4168b39859738a0e91388d252286480c7331b3f71a517281:Splice.Api.Token.TransferInstructionV1:TransferFactory"
HOLDING_INTERFACE="718a0f77e505a8de22f188bd4c87fe74101274e9d4cb1bfac7d09aec7158d35b:Splice.Api.Token.HoldingV1:Holding"
TRANSFER_INSTRUCTION_INTERFACE="55ba4deb0ad4662c4168b39859738a0e91388d252286480c7331b3f71a517281:Splice.Api.Token.TransferInstructionV1:TransferInstruction"

# Utility templates
ALLOCATIONFACTORY_TEMPLATE="#utility-registry-app-v0:Utility.Registry.App.V0.Service.AllocationFactory:AllocationFactory"
MINTREQUEST_TEMPLATE="#utility-registry-app-v0:Utility.Registry.App.V0.Model.Mint:MintRequest"
