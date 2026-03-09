#!/usr/bin/env bash

## =================================================================================================
## Purpose: Configurations for this example, amend variables as needed.
## Script: source.sh
## =================================================================================================

# Users's details
USER_TOKEN="<PASTE_JWT_TOKEN_HERE>"
USER_PARTY_ID="holder::1220d301ababbed7bc8d6f6a80ce16f33933a7274a3013241b7fb373ca7e4f0d6567"

# Filtering criteria
ADMIN_PARTY_ID="registrar::1220d301ababbed7bc8d6f6a80ce16f33933a7274a3013241b7fb373ca7e4f0d6567"
INSTRUMENT_ID="INST"
MIN_AMOUNT="5.0"

# JSON API endpoint (pick one)
# - Remote (TestNet/MainNet/other): HTTP_JSON_API="https://<your-host>/api/json-api"
# - DevNet (example):               HTTP_JSON_API="https://utility.utility.cnu.devnet.da-int.net/api/json-api"
# - Local (example):                HTTP_JSON_API="http://localhost:8001/api/json-api"
HTTP_JSON_API="http://localhost:8001/api/json-api"

# Token standard holding interface, may change when new versions of splice exists
HOLDING_INTERFACE="718a0f77e505a8de22f188bd4c87fe74101274e9d4cb1bfac7d09aec7158d35b:Splice.Api.Token.HoldingV1:Holding"

# Utility holding template, may change when a new version of the utility exists
HOLDING_TEMPLATE="dd3a9f2d51cc4c52d9ec2e1d7ff235298dcfb3afd1d50ab44328b1aaa9a18587:Utility.Registry.Holding.V0.Holding:Holding"
