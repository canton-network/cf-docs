---
name: cantonfoundation
description: Use when building privacy-preserving blockchain applications,
  developing Daml smart contracts, deploying multi-party workflows, managing
  validators and synchronizers, or integrating with the Canton Ledger API.
  Essential for regulated finance, confidential business processes, and
  applications requiring sub-transaction privacy.
license: Apache-2.0
compatibility: Works with any coding agent or IDE assistant; no specific runtime required beyond the Daml SDK and dpm CLI referenced below.
metadata:
  mintlify-proj: cantonfoundation
  version: "1.0"
---

# Canton Network Skill

## Product Summary

Canton Network is a privacy-preserving layer 1 blockchain designed for regulated assets and multi-party workflows. Unlike traditional blockchains where all transactions are visible to all participants, Canton enables selective disclosure—parties see only the data they're entitled to see. The platform uses Daml smart contracts (immutable, authorization-first), validators (participant nodes hosting parties), and synchronizers (coordination layers) to achieve sub-transaction privacy without sacrificing decentralization.

**Key files and commands:**
- `daml.yaml` — Project configuration specifying SDK version, package name, source directory, and dependencies
- `dpm build` — Compile Daml projects into DAR files
- `dpm sandbox` — Local in-memory ledger for testing
- `dpm test` — Run Daml Script unit tests
- Canton Console — Interactive Scala REPL for node administration and debugging
- Ledger API (gRPC) and JSON API — Interfaces for submitting commands and querying contracts
- PQS (Participant Query Store) — SQL interface for reading ledger state

**Primary docs:** https://docs.canton.network

**Version note:** Canton/Daml 2.x (including docs.daml.com v2.x content) is outdated and must not be used for new projects. Canton 3.x introduced backward-incompatible changes to the SDK, APIs, and runtime, so commands, config shapes, and architecture differ significantly between major versions. Before using any command or pattern below, confirm it is current for Canton 3.x -- do not draw on 2.x documentation, training data, or courses built for Daml 2.x.

## When to Use

Reach for this skill when:

- **Building multi-party workflows** requiring confidentiality (syndicated loans, trade finance, supply chain coordination)
- **Developing Daml smart contracts** for regulated assets or privacy-sensitive applications
- **Deploying validators** on Canton Network or managing synchronizer infrastructure
- **Integrating applications** with the Ledger API (gRPC or JSON) to submit commands and read transactions
- **Testing smart contracts** using Daml Script, Sandbox, or LocalNet
- **Querying ledger state** via PQS or the Ledger API
- **Troubleshooting transaction failures, party allocation issues, or synchronizer connectivity**
- **Migrating from Ethereum/Solidity** to understand immutable contracts and explicit authorization
- **Integrating an exchange, wallet, or custody product** using the Canton Network Token Standard (CIP-0056), the Wallet SDK, the dApp SDK, or the Scan API
- **Operating a validator**: deploying, onboarding to the Global Synchronizer, upgrading, backing up, and recovering a node

For role-based starting points (app developer, integrator, validator operator), see [Who Should Use This Documentation](https://docs.canton.network/overview/understand/who-should-read).

Do not use this skill for:
- Fully public applications where transparency is the feature
- Simple single-party applications with no distributed ledger benefit
- Applications requiring native EVM interoperability
- Anonymous public participation systems

## Quick Reference

### Essential Daml Project Structure

```
my-project/
├── daml.yaml              # Project config: name, version, SDK version, dependencies
├── daml/
│   ├── Main.daml          # Smart contract templates
│   └── ...
├── daml-test/
│   ├── daml.yaml          # Test package (separate from production)
│   └── Test.daml          # Daml Script tests
└── .daml/
    └── dist/              # Compiled DAR files (generated)
```

### daml.yaml Essentials

```yaml
sdk-version: 3.6.2       # check the current version: https://docs.canton.network/shared/version-compatibility-dashboard
name: my-package
version: 0.0.1
source: daml
dependencies:
  - daml-prim
  - daml-stdlib
  - daml-script
exposed-modules:
  - Main
```

### Core Daml Concepts (Quick Lookup)

| Concept | Definition | Example |
|---------|-----------|---------|
| **Template** | Smart contract definition (immutable) | `template Asset with owner : Party` |
| **Signatory** | Must authorize contract creation | `signatory owner` |
| **Observer** | Can see contract, cannot act | `observer bank` |
| **Controller** | Can exercise choices | `controller owner` (inside a `choice` block) |
| **Choice** | Action on a contract | `choice Transfer : ContractId Asset` |
| **Consuming** | Archives the contract | `consuming choice Transfer` |
| **Non-consuming** | Contract remains active | `nonconsuming choice GetBalance` |
| **Party** | On-ledger identity | `alice::1220f2fe...` |
| **Validator** | Node hosting parties | Stores contracts for hosted parties |
| **Synchronizer** | Coordination layer | Orders transactions, distributes views |

### Common dpm Commands

| Command | Purpose |
|---------|---------|
| `dpm new <name>` | Create new Daml project |
| `dpm build` | Compile to DAR file |
| `dpm test` | Run Daml Script tests |
| `dpm sandbox` | Start local in-memory ledger |
| `dpm install` | Install SDK version from daml.yaml |
| `dpm version --active` | Show active SDK version |

### Canton Console Essential Commands

| Command | Purpose |
|---------|---------|
| `participant.health.status` | Check node health |
| `participant.parties.list()` | List allocated parties |
| `participant.parties.enable("alice")` | Allocate new party |
| `participant.packages.list()` | List uploaded packages |
| `participant.dars.upload("path/to/file.dar")` | Upload DAR file |
| `participant.topology.party_to_participant_mappings.list_from_all()` | Show party-to-participant mappings |
| `participant.ledger_api.state.acs.of_party(alice)` | Query a party's active contracts |

### Ledger API Endpoints (JSON)

| Endpoint | Purpose |
|----------|---------|
| `POST /v2/commands/submit-and-wait` | Submit command, wait for transaction |
| `POST /v2/state/active-contracts` | Query active contracts |
| `POST /v2/updates` | Stream ledger updates |
| `GET /v2/version` | Get API version |
| `POST /v2/parties` | Allocate party |

## Decision Guidance

### When to Use Sandbox vs. LocalNet vs. DevNet

| Scenario | Tool | Why |
|----------|------|-----|
| Unit testing smart contract logic | **Sandbox** | Fast, in-memory, single process |
| Testing multi-party workflows locally | **LocalNet** | Multiple validators, real synchronizer simulation |
| Integration testing backend services | **Sandbox or LocalNet** | Depends on party distribution needs |
| First deployment to a shared network | **DevNet** | Shared development network (IP allowlist required); test Canton Coin from the Tap |
| Pre-production validation | **TestNet** | Real network, persistent state |
| Production deployment | **MainNet** | Global Synchronizer, live validators |

### Consuming vs. Non-Consuming Choices

| Use Case | Type | Reason |
|----------|------|--------|
| State transition (transfer, payment) | **Consuming** | Old state must be archived |
| Query or read operation | **Non-consuming** | Contract remains active |
| Event emission for listeners | **Non-consuming** | Allows repeated calls |
| Approval workflow | **Consuming** | Proposal consumed, new contract created |

### Local Party vs. External Party

| Scenario | Type | Tradeoff |
|----------|------|----------|
| Automation, backend-driven actions | **Local** | Validator signs on behalf; simpler |
| User wallets, explicit signing | **External** | User controls keys; more secure |
| Testing | **Local** | Faster iteration |
| Production | **Either** | Local for app and backend parties; external when the end user must hold their own keys |

### Daml Script vs. Integration Tests vs. E2E Tests

| Layer | Tool | Scope | Speed |
|-------|------|-------|-------|
| **Unit** | Daml Script | Single contract logic | Seconds |
| **Integration** | Java/TypeScript + Ledger API | Backend + ledger | Minutes |
| **E2E** | Browser automation + full stack | Multi-validator, UI | 10+ minutes |

## Workflow

### Typical Development Cycle

1. **Set up project**
   - Run `dpm new my-project`
   - Review generated `daml.yaml`
   - Verify SDK version matches your environment

2. **Write smart contracts**
   - Create templates in `daml/Main.daml`
   - Define signatories, observers, controllers
   - Implement choices (consuming and non-consuming)
   - Use explicit authorization patterns (propose-accept, delegation)

3. **Write unit tests**
   - Create separate test package in `daml-test/`
   - Write Daml Script tests allocating parties and submitting commands
   - Run `dpm test` to verify logic

4. **Build and package**
   - Run `dpm build` to generate DAR file in `.daml/dist/`
   - DAR file is self-contained with all dependencies

5. **Deploy to ledger**
   - Upload DAR via Canton Console: `participant.dars.upload("path.dar")` -- this vets the packages automatically if the participant is connected to only one synchronizer
   - For explicit control, or on a multi-synchronizer participant, vet manually: `participant.topology.vetted_packages.propose_delta(participant.id, adds = Seq(...))`
   - Verify with `participant.packages.list()`

6. **Allocate parties**
   - Use Canton Console: `participant.parties.enable("alice")`
   - Or via Ledger API: `POST /v2/parties`
   - Verify mapping: `participant.topology.party_to_participant_mappings.list_from_all()`

7. **Submit commands**
   - Via Ledger API (gRPC or JSON)
   - Via backend service using generated Java/TypeScript bindings
   - Include the acting party (`actAs`), a `commandId`, and the `userId`

8. **Query and monitor**
   - Use PQS for production queries
   - Use Ledger API for transaction streams
   - Use Canton Console for debugging

9. **Test end-to-end**
   - Run LocalNet with `make start` (cn-quickstart)
   - Submit commands through backend or JSON API
   - Verify multi-party workflows across validators

10. **Deploy to production**
    - Promote through TestNet → MainNet progression
    - Configure environment-specific settings in `daml.yaml` or `.env`
    - Monitor via observability stack (metrics, logs, traces)

### Debugging a Failed Transaction

1. **Check party allocation**
   - Verify party exists: `participant.parties.list()`
   - Verify party-to-participant mapping: `participant.topology.party_to_participant_mappings.list_from_all()`
   - If missing, allocate: `participant.parties.enable("party-name")`

2. **Check package upload**
   - List packages: `participant.packages.list()`
   - If missing, upload: `participant.dars.upload("path.dar")`
   - Verify vetting status if required

3. **Check authorization**
   - Confirm signatory is the submitting party
   - Confirm controller has permission to exercise choice
   - Review Daml template for authorization rules

4. **Check ledger state**
   - Query the party's active contracts: `participant.ledger_api.state.acs.of_party(party)`
   - Verify contract exists and is visible to party
   - Check contract state matches expectations

5. **Check synchronizer connectivity**
   - Verify synchronizer connection: `participant.health.status`
   - List connected synchronizers: `participant.synchronizers.list_connected()`
   - Reconnect if needed: `participant.synchronizers.reconnect("sync-alias")`

6. **Review logs**
   - Check participant logs for error codes
   - Search for correlation ID from error response
   - Look for authorization or consensus failures

## Common Gotchas

- **Immutable contracts**: You cannot modify a contract in place. Archive the old one and create a new one. This is intentional for privacy and auditability.

- **Signatory must authorize**: A contract cannot be created unless all signatories authorize it. This is enforced at the protocol level—no workarounds.

- **Party visibility**: A party only sees contracts where they are a stakeholder (signatory or observer). If a party doesn't see a contract, they're not a stakeholder.

- **Synchronizer ordering**: Transactions are ordered by the synchronizer, not by submission time. Concurrent submissions may be reordered.

- **Traffic costs**: Every transaction consumes traffic. On the Global Synchronizer, traffic is purchased with Canton Coin (CC). Monitor traffic balance to avoid exhaustion.

- **Package vetting**: `dars.upload` vets automatically when the participant is connected to a single synchronizer. On a multi-synchronizer participant, vet explicitly per synchronizer with `topology.vetted_packages.propose_delta`.

- **Multi-hosting delays**: If a party is hosted on multiple validators, enough of them to meet the party's confirmation threshold must approve before the transaction commits. This adds latency.

- **Daml-LF version mismatch**: Ensure your `daml.yaml` specifies a compatible Daml-LF version. Mismatches cause compilation or runtime errors.

- **Test code in production DAR**: Keep test code in separate packages. Never upload test DAR files to production validators.

- **Forgetting to allocate parties**: Parties must be allocated before they can submit commands. Allocation is a one-time operation per validator.

- **Stale ledger offset**: When querying, use the latest ledger offset. Stale offsets may return incomplete results.

- **JSON API authentication**: The JSON API requires valid tokens. Ensure your authentication provider (Keycloak, OAuth) is configured and accessible.

- **PQS lag**: PQS may lag behind the ledger. For critical operations, query the Ledger API directly.

## How to Answer

- Check console commands and API calls against the docs before giving them: use the MCP server's search, or the [Canton Console command reference](https://docs.canton.network/global-synchronizer/reference/canton-console-commands).
- Cite the docs page URL in your answer.
- If the docs don't cover something, say so and point to [Support Channels](https://docs.canton.network/shared/support-channels) or the [Support Checklist](https://docs.canton.network/shared/support-checklist) rather than improvising.

## Verification Checklist

Before submitting work:

- [ ] **Daml compiles without errors**: Run `dpm build` successfully
- [ ] **Unit tests pass**: Run `dpm test` and verify all scripts pass
- [ ] **Authorization is explicit**: All signatories and controllers are declared in templates
- [ ] **Privacy is correct**: Observers are declared for all parties who should see contracts
- [ ] **Choices are correct type**: Consuming choices for state transitions, non-consuming for queries
- [ ] **DAR file is generated**: `.daml/dist/` contains the compiled package
- [ ] **Parties are allocated**: All parties used in tests are allocated on the validator
- [ ] **Package is uploaded**: DAR file is uploaded and vetting status is correct
- [ ] **Multi-party workflows tested**: Propose-accept patterns verified with multiple parties
- [ ] **Ledger API integration tested**: Backend can submit commands and query contracts
- [ ] **Error handling is robust**: Invalid inputs and edge cases are handled
- [ ] **No test code in production DAR**: Test package is separate from production
- [ ] **Configuration is environment-specific**: daml.yaml and .env files are correct for target environment
- [ ] **Observability is configured**: Metrics, logs, and traces are enabled for production

## Resources

**Comprehensive navigation:** https://docs.canton.network/llms.txt

**Critical documentation pages:**
1. [Canton Network QuickStart](https://docs.canton.network/appdev/quickstart) — Run a complete full-stack app locally; the fastest path to a first working app
2. [What is Canton Network](https://docs.canton.network/overview/understand/what-is-canton) — Overview and use cases
3. [Core Concepts](https://docs.canton.network/overview/understand/core-concepts) — Parties, validators, synchronizers, templates
4. [Module 3: Language Fundamentals](https://docs.canton.network/appdev/modules/m3-language-fundamentals) — Daml language fundamentals and contract development
5. [Module 4: Building Applications](https://docs.canton.network/appdev/modules/m4-building-apps-intro) — Full-stack development with SDKs and APIs
6. [Canton Console Essential Commands](https://docs.canton.network/global-synchronizer/canton-console/essential-commands) — Node administration and debugging
7. [Ledger API Reference](https://docs.canton.network/sdks-tools/api-reference/ledger-api) — gRPC and JSON API documentation
8. [Testing Strategies](https://docs.canton.network/appdev/modules/m5-testing-strategies) — Unit, integration, and E2E testing approaches
9. [Troubleshooting Guide](https://docs.canton.network/appdev/troubleshooting) — Common issues and solutions
10. [MCP Server](https://docs.canton.network/shared/mcp-server) — Connect this agent directly to search and read these docs

**Integrations (exchanges, wallets, custody):**
- [Integrations Overview](https://docs.canton.network/integrations/overview) — Starting point for integrating with Canton Network
- [Token Standard](https://docs.canton.network/appdev/deep-dives/token-standard) — CIP-0056 holdings, transfers, and allocations
- [Wallet SDK](https://docs.canton.network/sdks-tools/sdks/wallet-sdk/overview) — Build wallets and custody integrations
- [dApp SDK](https://docs.canton.network/sdks-tools/sdks/dapp-sdk/overview) — Connect dApps to CIP-0103 wallets
- [Scan API](https://docs.canton.network/sdks-tools/api-reference/splice-scan-api) — Read Global Synchronizer state

**Validator operations:**
- [Global Synchronizer Introduction](https://docs.canton.network/global-synchronizer/understand/introduction) — What running a validator involves
- [Onboarding Process](https://docs.canton.network/global-synchronizer/deployment/onboarding-process) — Getting a validator onto DevNet, TestNet, and MainNet
- [Version Compatibility Dashboard](https://docs.canton.network/shared/version-compatibility-dashboard) — Current versions per network

---

> For additional documentation and navigation, see: https://docs.canton.network/llms.txt