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

Native tabs on `insurance_space.html`: Markets & Access, Connectivity, Submissions. Company detail: connectivity section. Policy detail: four optional fields. Copy must not claim free access to every carrier.

## Phase 7 — Real carrier

Only after official docs + authorization. Certification checklist must pass before `environment=production`. Skeleton connectors remain until then.

## Status in this repository

The `regiconnect` Django app implements Phases 1–6 against the **mock** connector, plus a Phase 7 **gate**: the `unspecified` skeleton raises `MissingCarrierSpec`, and production cannot be enabled without a passing certification run plus explicit approval. No real carrier URLs or credentials are invented.

Discovery maps in this folder remain the source of truth for what already existed in Insurance Space.

Official spec, appointment, sandbox, auth/submit/quote/bind/download/docs/webhook tests as supported, idempotency, rate limits, security review, explicit production approval. Software cannot create contractual access.
