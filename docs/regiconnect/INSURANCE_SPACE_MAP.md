# Insurance Space map

Entry: `GET /dashboard/inventory/<space_id>/` when `Space.key == "insurance"` (`core.views.inventory_detail`). Template: `templates/core/insurance_space.html`.

Tabs (native `switchTab`, persisted in `localStorage`):

| Tab id | Label | Gate |
|---|---|---|
| `insurance` | Insurance CRM | Space access |
| `quote-pipeline` | Quote Pipeline | View: owner/manager/`can_deal_with_insurance` |
| `companies` | Companies | `can_view_banking` (owners always) |
| `banking` | Finance | same |
| `reporting` | Reporting Center | Space access |
| `esign` | E-Signature | Space access (e-sign views do not require `can_deal_with_insurance`) |
| `targets` | Targets & Forecast | Space access |
| `daily-payments` | Daily Payments | Space access (clear requires banking) |
| `agents` | Agent Auditing | Space access |
| `regi-markets` | Markets & Access | `can_view_regiconnect` (owners bypass) |
| `regi-connectivity` | Connectivity | same |
| `regi-rater` | Regi Rater | same; comparative quoting desk (CRM/OCR capture → shop markets → compare → Quote Pipeline). Legacy `?tab=regi-submissions` redirects here. |

**Regi Rater** is the single agent quoting tab. One-market `Submission` still exists for tests and bind MOCK; agents do not use a separate Submissions tab.

## Module responsibilities (preserve)

**Insurance CRM** — `InsurancePolicy` rows for the org, filtered by quote-date period. Add/edit/delete policy modals post to `add-insurance-policy` / `edit-insurance-policy`. Detail page: `insurance-policy-detail`. DEC import creates or updates policies from uploaded PDFs.

**Quote Pipeline** — `InsuranceQuoteLead` kanban. This is **agent distribution**, not a comparative rater. Create → optional auto round-robin (`insurance_quote_distribution.py`) among `insurance_agent` members with `can_deal_with_insurance`. Stages: assigned / quoting / quoted / won / lost. No FK to `InsurancePolicy`. No premium on the lead.

**Companies** — `InsuranceCompany` cards: license, BR/BC broker arrangement, bound-policy summaries, ledger. This is the market the agency places with, not the agency itself.

**Finance** — `BankAccount` / `BankTransaction` plus policy commission fields. Ledger PDFs are reports over those tables.

**Reporting Center** — PDF exporters in `core/insurance_report_views.py`.

**E-Signature** — `InsuranceESignEnvelope` (draft → email token → public `/sign/<token>/`).

**Targets & Forecast** — `InsuranceMonthlyTarget`, `InsuranceLineTarget`, `InsuranceMarketPremiumAssumption` (LOB average premium planner — not a marketplace).

**Daily Payments** — `DailyPaymentTransaction` cashbook (new business, renewal, monthly, endorsement, misc).

**Agent Auditing** — memberships with `can_deal_with_insurance`; `AgentActivityEvent` / attendance used by distribution.

## Adjacent, not Insurance Space

- **ClientIntake** is PSB/DMV public intake; insurance fields are strings, not `InsurancePolicy`.
- **TLC Space** has its own policy/carrier-name registry (`TLCCarrier`). Do not merge into RegiConnect Markets.
- **Email marketing** can assign CRM contacts to insurance agents; it is not quoting.

## Quote systems (do not duplicate)

1. Pipeline lead (`InsuranceQuoteLead`) — work queue / agent distribution. No premium column.
2. CRM policy with `stage=quote` — book of business.
3. `regiconnect.CanonicalQuote` — rating/submission result (versioned). Comparative shop happens in Regi Rater; select feeds (1). Mock bind can still create a labeled MOCK policy in (2).

Won pipeline leads do **not** create policies. Do not invent a fourth quote board.
