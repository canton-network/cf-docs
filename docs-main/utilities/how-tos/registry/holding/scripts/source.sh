#!/usr/bin/env bash

## =================================================================================================
## Purpose: Configurations for this example, amend variables as needed.
## Script: source.sh
## =================================================================================================

# users's details
USER_TOKEN="eyJhbGciOiJIUzI1NiJ9.eyJzY29wZSI6ImRhbWxfbGVkZ2VyX2FwaSIsImlhdCI6MTc1OTk5MjE0NiwiYXVkIjoiaHR0cHM6Ly91dGlsaXR5LmNhbnRvbi5uZXR3b3JrIiwic3ViIjoiaG9sZGVyIn0.4zuioSDoiysXfNLmobyW0xqXmJEY1tnvX7QOnHv1ASU"
USER_PARTY_ID="holder::1220d301ababbed7bc8d6f6a80ce16f33933a7274a3013241b7fb373ca7e4f0d6567"

# filtering criteria
ADMIN_PARTY_ID="registrar::1220d301ababbed7bc8d6f6a80ce16f33933a7274a3013241b7fb373ca7e4f0d6567"
INSTRUMENT_ID="INST"
MIN_AMOUNT="5.0"

# endpoint for json-api
HTTP_JSON_API="http://localhost:8001/api/json-api"

# token standard holding interface, may change when new versions of splice exists
HOLDING_INTERFACE="718a0f77e505a8de22f188bd4c87fe74101274e9d4cb1bfac7d09aec7158d35b:Splice.Api.Token.HoldingV1:Holding"

# utility holding template, may change when a new version of the utility exists
HOLDING_TEMPLATE="dd3a9f2d51cc4c52d9ec2e1d7ff235298dcfb3afd1d50ab44328b1aaa9a18587:Utility.Registry.Holding.V0.Holding:Holding"
