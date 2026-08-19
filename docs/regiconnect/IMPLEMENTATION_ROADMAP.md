# Implementation roadmap

## Phase 0 — Discovery (this folder)

Ten maps reflecting the inspected repo. No carrier endpoints.

## Phase 1 — Foundation

Django app `regiconnect`: MarketProfile, Appointment, ProducerCode, Connector registry, Connection, capabilities, audit, idempotency, correlation, encrypted secret references. Mock connector `health_check` only at first, then full mock in Phase 3.

## Phase 2 — Runtime

Celery jobs, retryable vs terminal errors, DLQ, outbox publisher, correlation IDs on every job.

## Phase 3 — Engines + mock carrier

Submission / canonical quote / bind state machines. Mock simulates quote, referral, decline, bind, timeout, 429, 500, duplicates. No real URLs.

## Phase 4 — Existing Insurance Space

- Build canonical submission from `Client` / lead / policy fields.
- Persist quotes onto `InsuranceQuoteLead` via connectivity row + `assign_lead` when source is REGI_CONNECT.
- Bind creates/updates `InsurancePolicy` + `PolicyConnectivity`.
- Bound event may insert `DailyPaymentTransaction` (misc/new_business) without a second ledger.

## Phase 5 — Exchange

Document metadata + FileField, inbound transaction parser hook, webhook receiver, SFTP job models + host-key requirement, ACORD mapper stub (versioned, no invented forms), reconciliation exception rows.

## Phase 6 — UI

Native tabs on `insurance_space.html`: Markets & Access, Connectivity, Regi Rater (quoting desk). Company detail: connectivity section. Policy detail: four optional fields. Copy must not claim free access to every carrier.

## Phase 7 — Real carrier

Only after official docs + authorization. Certification checklist must pass before `environment=production`. Skeleton connectors remain until then.

## Status in this repository

RegiConnect Phases 1–6 exist against the **mock** connector, with a Phase 7 **gate** (`MissingCarrierSpec`, certification before production). No real carrier URLs or credentials are invented.

**Regi Rater is not implemented.** Discovery for the rater is `REGI_RATER_ARCHITECTURE.md`. Do not start rater models until explicit approval after the Phase 0 assessment.

## Regi Rater phases (after approval)

### Rater Phase 0 — Discovery (this folder)

Maps updated; `REGI_RATER_ARCHITECTURE.md` added. No rater tables yet.

### Rater Phase 1 — Foundation (in repo)

`RatingRequest`, `RatingJob`, `RatingExtension`, `RatingError`; `CanonicalQuote` source/premium class/versioning; `MarketProfile.market_channel`; state machine + audit. **No** concurrent live UI. **No** real carrier connector.

### Rater Phase 2 — Orchestrator (in repo)

Eligibility uses existing access/appetite; assigned risk and unspecified connectors are excluded with reasons; concurrent job dispatch via existing `ConnectorJob`; partial vs completed status; mock quotes are not ingested into Quote Pipeline; retryable errors stay in-flight. **No** comparison UI. **No** real carrier connector.

### Rater Phase 3 — Mock providers (in repo)

Mock scenarios: quote, decline, refer, timeout, delay, invalid, error. Delayed quotes stay in-flight until resume. Duplicate versions never overwrite.

### Rater Phase 4 — Insurance Space UI (in repo)

Native **Regi Rater** tab. CRM client/vehicle reuse. Comparison table with MOCK / TEST labels. Select quote hands off to existing Quote Pipeline (`quote_source=regi_rater`). Bind is hidden for estimated/mock premiums.

### Rater Phase 5 — Real connectivity reuse

Use existing connector runtime, secrets, certification. Capability matrix drives the UI.

### Rater Phase 6 — First real market

Only with official docs + authorization + sandbox + certification + production approval.

### Rater Phase 7 — Additional markets + NYAIP

Isolated connectors. NYAIP only if official Plan integration exists; otherwise tracking/DEC only.

Official spec, appointment, sandbox, auth/submit/quote/bind/download/docs/webhook tests as supported, idempotency, rate limits, security review, explicit production approval. Software cannot create contractual access.
