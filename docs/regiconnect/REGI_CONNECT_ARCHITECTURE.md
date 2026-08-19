# RegiConnect architecture

RegiConnect is a **bounded context inside Insurance Space**, implemented as Django app `regiconnect`. It is not a new Space, CRM, quote pipeline, company book, finance ledger, or policy master.

## Flow (target)

```
Existing CRM (Client / drivers / vehicles / policy fields)
  → Market Access (appointment + producer code + state + LOB + connection)
  → Appetite (configurable rules, not hardcoded in connectors)
  → Connector adapter
  → Authorized market (when spec exists) or Mock
  → Canonical quote / bind / document / inbound txn
  → Existing Quote Pipeline (distribution)
  → Existing InsurancePolicy (bind)
  → Existing DailyPayment / BankTransaction (finance events)
```

## Canonical vs carrier

RegiManager owns the canonical model. Carrier JSON/XML/ACORD exists only inside `regiconnect/connectors/<slug>/`. Core never imports carrier schemas.

## Attach to existing rows

- **Market:** 1:1 `MarketProfile` on `InsuranceCompany` (type carrier/MGA/wholesaler/aggregator/distribution_partner/other; NAIC; states; LOBs). Companies tab stays the card.
- **Quotes:** `QuoteLeadConnectivity` 1:1 on `InsuranceQuoteLead` (source, premium snapshot, submission, external ref, status). Pipeline UI unchanged except metadata.
- **Policies:** `PolicyConnectivity` 1:1 on `InsurancePolicy` (external policy number, last sync, status). Policy detail stays Driver / Vehicle / Overview plus a small connectivity chip.
- **Finance:** create `DailyPaymentTransaction` / `BankTransaction` through existing models; never a second GL.

## Connector SDK

Python ABC `InsuranceConnector`:

- `health_check`, `validate_connection`, `capabilities`
- `submit_submission`, `get_submission_status`
- `request_quote`, `get_quote`
- `request_bind`, `get_bind_status`
- `get_policy`, `download_transactions`, `download_documents`
- `handle_webhook`

Missing capability → `CapabilityNotSupported`. Missing official spec → `MissingCarrierSpec`. Never invent endpoints.

## Runtime

Celery task `regiconnect.tasks.run_connector_job`:

```
API/command → Outbox row → Worker → Connector → persist raw payload (access-controlled)
  → idempotency key unique constraint
  → on retryable error: exponential backoff
  → on exhausted retries: DeadLetterItem
```

HTTP requests never block on slow carriers.

## Environments

Connection.environment: `sandbox` | `certification` | `production`. Production requires certification records + `production_approved_at` + `production_approved_by`. Never copy production credentials into development.

## Security

- Tenant filter on every queryset.
- Secrets: `credential_reference` only; Fernet/local encrypted store in dev; mask in logs.
- Webhooks: HMAC + timestamp + replay window + persist-before-process.
- SFTP: refuse production connect without host key fingerprint.
- Appointments are never auto-ACTIVE from software alone.

## Carrier portal (future)

`audience` field on some records (`agency` vs `market`). No carrier UI in early phases. Carrier users must not see agency CRM except data present on authorized transactions.
