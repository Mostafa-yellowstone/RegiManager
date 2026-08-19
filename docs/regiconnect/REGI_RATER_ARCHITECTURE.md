# Regi Rater architecture

Regi Rater is a **bounded context inside Insurance Space**. It is not EZLynx, not a second CRM, not a second Quote Pipeline, and not a premium calculator.

RegiConnect remains the connectivity layer (access, appointments, producer codes, appetite, connectors, jobs, bind, documents). Regi Rater orchestrates **comparative rating** on top of that layer.

```
CRM (Client / Vehicle)
  → Regi Rater (RatingRequest + eligibility + compare)
    → RegiConnect (Market Access + Connection + ConnectorJob)
      → Authorized rating source (when spec exists) or labeled MOCK
    → CanonicalQuote versions
  → Select quote
  → Existing InsuranceQuoteLead (distribution only)
  → Bind via existing BindTransaction → InsurancePolicy → Daily Payments
```

## What already exists (do not rebuild)

- Canonical payload from `Client` + `Vehicle` (`regiconnect/canonical.py`).
- Per-market `Submission` + `CanonicalQuote` + `QuoteLeadConnectivity` (1:1 on a lead).
- Market access + appetite evaluation.
- Celery `ConnectorJob` with mock inline fallback.
- Insurance Space tabs: Markets & Access, Connectivity, Regi Rater (Submissions merged into Rater).
- Mock connector that **must stay labeled MOCK / TEST**. Its premium is not a carrier rate.
- EZLynx: org URL field only. Not a rating provider. Must not become required.

## What does not exist yet

- Quote comparison UI and select-quote pipeline handoff: **shipped** (estimated/mock cannot bind).
- Native Regi Rater tab: **shipped**.
- Any Progressive / National General / NYAIP rating endpoint.
- NYAIP official electronic filing.

## Rating request (proposed)

New rows in `regiconnect` only:

- `RatingRequest` — org, client FK, state, LOB, coverage, effective date, status, correlation_id, idempotency_key, canonical snapshot JSON.
- `RatingJob` — FK request + market + connection, status, last_error, submission FK nullable.
- `RatingExtension` — per market carrier-specific answers (JSON), not CRM columns.
- Reuse `CanonicalQuote` (add `rating_job` FK, `quote_source`, `premium_class`, `environment`). Do not create `CarrierQuote` if this extension is enough.

Lifecycle: DRAFT → VALIDATING → ELIGIBILITY_CHECK → READY → RATING → PARTIAL_RESULTS → COMPLETED | NO_MARKET | FAILED | CANCELLED | EXPIRED.

## Eligibility (reuse, do not duplicate)

For each `MarketProfile` + `Connection`:

1. `evaluate_market_access` (appointment, producer code, active connection, state, LOB).
2. `evaluate_appetite`.
3. Connector capability `supportsRating` / `supportsQuote` from the connection matrix — **never assume YES**.
4. Market channel: VOLUNTARY vs ASSIGNED_RISK. NYAIP is ASSIGNED_RISK; agents cannot pick a servicing carrier.

Excluded markets store a reason string on the job (INELIGIBLE / UNAVAILABLE / NO_RATING_CAPABILITY).

## Orchestrator

Lives in `regiconnect/rater/` (or `regirater` package inside the same Django app to avoid a second app unless isolation requires it). It must not import Progressive schemas.

- Concurrent jobs via existing `dispatch_job` / Celery.
- Partial UI: poll `inventory-detail?tab=regi-rater` or JSON under `/api/regiconnect/rater/...` (existing namespace, **not** `/api/v1/`).
- HTTP never waits on slow carriers.

## Quote pipeline handoff

Selecting a quote updates `CanonicalQuote.status=SELECTED` and creates/updates `InsuranceQuoteLead` + `QuoteLeadConnectivity` (premium snapshot, source `regi_connect` or `regi_rater`). Pipeline `assign_lead` unchanged.

Do not create `RegiQuotePipeline`.

## Assigned risk

Until official NYAIP documentation and producer authorization exist: track eligibility, documents, assignment reference, servicing carrier **as recorded after the Plan assigns**. No fake electronic assignment.

## Status

Phase 2 orchestrator is in `regiconnect/rater/orchestrator.py`. Comparison UI and pipeline select are shipped. Real carriers are **not**.

Mock quotes must use `quote_source=MOCK`, `premium_class=ESTIMATED`, and never appear as a carrier rate.

## First real market

Blocked on official spec + appointment + sandbox + certification + production approval. Skeleton `unspecified` continues to raise `MissingCarrierSpec`.
