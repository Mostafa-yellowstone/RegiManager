# API map

There is **no** `/api/v1/` prefix in this repo. New connectivity HTTP should follow existing patterns, not invent a second versioning scheme.

## Dashboard (session + CSRF)

Insurance Space HTML: `inventory-detail`. Named routes include:

- Policies: `add-insurance-policy`, `edit-insurance-policy`, `insurance-policy-detail`, DEC import, document upload, installment toggle.
- Companies: `add-insurance-company`, `insurance-company-detail`, license edit, docs, ledger fragment.
- Quote pipeline: `create-quote-lead`, assign/stage/edit/delete, distribution config, off-days, `quote-records`.
- Daily payments, finance bank txs, reports PDFs, e-sign, targets.

Many POSTs return JSON when `XMLHttpRequest`.

## Companion / owner (DRF Token or Session)

Prefix `/api/`. Org header `X-Organization-Id` (or `organization_id` query).

- Auth: `POST /api/auth/login/`, logout, me.
- Viewsets: `/api/clients/`, `/api/vehicles/`, `/api/service-records/`.
- Owner: `/api/owner/insurance/policies/`, targets, finance, spaces, TLC, inventory, notifications.
- Agent portal: `/api/agent/portal/home/`, tasks, attendance, activity.
- Portal live (session `@login_required`): `/api/portal/quote-pipeline/`, `/api/portal/quote-distribution/`, notifications wait/stream.

OpenAPI: `/api/schema/`, swagger, redoc (authenticated).

## Public

- PSB intake `/intake/<token>/`.
- E-sign signer `/sign/<token>/` (CSRF-exempt for the signer).
- Old public insurance intake URLs were removed (`0162_quote_pipeline_remove_intake`).

## Proposed RegiConnect HTTP (not `/api/v1/`)

- Session UI: Insurance Space extra tabs (same `inventory-detail` page).
- JSON: `/api/regiconnect/...` with Token+Session, `X-Organization-Id`, same pagination/errors as companion APIs.
- Inbound webhooks: `/api/regiconnect/webhooks/<connection_id>/` — signature verified, CSRF exempt, never returns secrets.
