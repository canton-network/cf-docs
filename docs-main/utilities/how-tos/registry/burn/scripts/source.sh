#!/usr/bin/env bash

## =================================================================================================
## Purpose: Configurations for this example, amend variables as needed.
## Script: source.sh
## =================================================================================================

# receiver's details
BURNER_TOKEN="eyJhbGciOiJIUzI1NiJ9.eyJzY29wZSI6ImRhbWxfbGVkZ2VyX2FwaSIsImlhdCI6MTc1OTk5MjEzMiwiYXVkIjoiaHR0cHM6Ly91dGlsaXR5LmNhbnRvbi5uZXR3b3JrIiwic3ViIjoiaXNzdWVyIn0.6wP8xNyQopoyKk_rGv9agcIK8TLyJVYLq3oRo983z8Q"
BURNER_PARTY_ID="issuer::1220d301ababbed7bc8d6f6a80ce16f33933a7274a3013241b7fb373ca7e4f0d6567"
BURNER_USER_ID="issuer"

# admin/registrar details
ADMIN_TOKEN="eyJhbGciOiJIUzI1NiJ9.eyJzY29wZSI6ImRhbWxfbGVkZ2VyX2FwaSIsImlhdCI6MTc1OTk5Nzk3OSwiYXVkIjoiaHR0cHM6Ly91dGlsaXR5LmNhbnRvbi5uZXR3b3JrIiwic3ViIjoicmVnaXN0cmFyIn0.zveSqMNH9LQIcGOXlyKoidGWJm0ldsj2R1gXiPzmAQk"
ADMIN_PARTY_ID="registrar::1220d301ababbed7bc8d6f6a80ce16f33933a7274a3013241b7fb373ca7e4f0d6567"
ADMIN_USER_ID="registrar"

# unique reference for the action
BURN_REF="burn-ref-002"

# update your asset and amount to be transferred
ASSET_ID="INST"
ASSET_AMOUNT="3.0"

# example 1
# BACKEND_API="https://api.utilities.digitalasset-dev.com/api/token-standard"
# HTTP_JSON_API="https://utility.demo.registry.digitalasset.com/api/json-api"
# example 2
BACKEND_API="http://localhost:8080/api/utilities"
HTTP_JSON_API="http://localhost:8001/api/json-api"

# token standard holding interface, may change when new versions of splice exists
# TRANSFERFACTORY_INTERFACE="55ba4deb0ad4662c4168b39859738a0e91388d252286480c7331b3f71a517281:Splice.Api.Token.TransferInstructionV1:TransferFactory"
HOLDING_INTERFACE="718a0f77e505a8de22f188bd4c87fe74101274e9d4cb1bfac7d09aec7158d35b:Splice.Api.Token.HoldingV1:Holding"
TRANSFER_INSTRUCTION_INTERFACE="55ba4deb0ad4662c4168b39859738a0e91388d252286480c7331b3f71a517281:Splice.Api.Token.TransferInstructionV1:TransferInstruction"

# utility templates, may change when new versions of utilities exists
# ALLOCATIONFACTORY_TEMPLATE="170929b11d5f0ed1385f890f42887c31ff7e289c0f4bc482aff193a7173d576c:Utility.Registry.App.V0.Service.AllocationFactory:AllocationFactory"
ALLOCATIONFACTORY_TEMPLATE="#utility-registry-app-v0:Utility.Registry.App.V0.Service.AllocationFactory:AllocationFactory"
BURNREQUEST_TEMPLATE="#utility-registry-app-v0:Utility.Registry.App.V0.Model.Burn:BurnRequest"
