# Risk register

| ID | Risk | Mitigation |
|---|---|---|
| R1 | Duplicate CRM / pipeline / finance | New app only references `Client`, `InsuranceQuoteLead`, `InsurancePolicy`, `InsuranceCompany`, `DailyPaymentTransaction`. |
| R2 | Two quote systems stay disconnected | Phase 4 writes pipeline connectivity + optional bind→policy; do not auto-convert won leads unless product asks. |
| R3 | QuoteLead has no premium | Store premium on `QuoteLeadConnectivity`, display on pipeline cards; do not overload `InsurancePolicy.stage=quote`. |
| R4 | Vehicle has no org FK | Always `client__organization_id=...`. |
| R5 | Invented carrier APIs | Mock + skeleton only; `MissingCarrierSpec` for real slugs. |
| R6 | Plaintext secrets | `credential_reference`; never serialize secrets in API/admin list. |
| R7 | Auto-appointment | Default appointment status `pending`; ACTIVE requires explicit manage permission. |
| R8 | Cross-tenant leak | Tests that org B cannot read org A connections/submissions. |
| R9 | Celery absent on VPS | Same eager/sync fallback as email marketing. |
| R10 | `core/models.py` size | All new tables in `regiconnect`. |
| R11 | RBAC as dotted strings | Add `can_view_regiconnect` / `can_manage_regiconnect` flags. |
| R12 | Breaking Insurance Space UI | Additive tabs; existing tab ids unchanged. |
| R13 | Claiming “free carrier access” | UI copy: connectivity infrastructure; carrier contract/appointment required. |
| R14 | Destructive migrations | Additive FKs/indexes only. |
| R15 | CI only runs `test core` | Update workflow to `test core regiconnect`. |
| R16 | EZLynx URL mistaken for API | Leave branding field alone; do not call it a connector. |
| R17 | PII in raw payloads | Restrict payload views to manage flag; never log SSN/DL/PAN. |
| R18 | Production deploy by push-to-main | Connectivity code is additive and gated; do not enable mock as a real market. |
| R19 | Mock premium mistaken for carrier rate | UI + `quote_source=MOCK` + environment SANDBOX; never map mock to Progressive/NG/NYAIP names. |
| R20 | Treat NYAIP as a voluntary carrier | Distinct ASSIGNED_RISK channel; no agent-picked servicing carrier; no fake AIP filing. |
| R21 | EZLynx as permanent rater backbone | Keep URL for public intake only; Regi Rater → RegiConnect → authorized market. |
| R22 | QuoteLeadConnectivity 1:1 vs many quotes | Select one canonical quote per handoff; do not overwrite history; version CanonicalQuote. |
| R23 | Building a second pipeline named Rater | Rater compares; `assign_lead` stays the only distributor. |
