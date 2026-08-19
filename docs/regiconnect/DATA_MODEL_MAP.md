# Data model map

Tenant root: `Organization`. Almost every insurance table has `organization` FK. `Vehicle` is the exception: scoped via `Client`.

## Tenant and access

- `Organization` — PSB; insurance branding, `insurance_ezlynx_quote_url`, intake flags.
- `OrganizationMembership` — unique `(organization, user)`; roles owner/manager/accountant/insurance_agent/agent; `can_*` flags; `accessible_spaces` M2M.
- `Space` — per-org cards; insurance is `key="insurance"`.

## CRM

- `Client` — name, SSN, DL, DOB, phones, addresses, commercial fields. Soft delete.
- `Vehicle` — VIN unique per active client; denormalized insurance *strings* (company name, policy number), not FKs.
- `ClientNote`, `Notification` (optional `policy` / `insurance_company` FKs).

## Companies and policies

- `InsuranceCompany` — unique `(organization, name)`; license dates; `broker_arrangement` br/bc. **No** NAIC, producer code, credentials, endpoints.
- `InsuranceCompanyDocument`
- `InsurancePolicy` — FK client + company; `policy_number`; stages quote/bound/endorsement; status; premium/broker_fee/commission_*; dates; named insured / VIN / plate denormalized. **No** external carrier id or last-sync.
- Children: `InsurancePolicyDocument`, `InsurancePolicyInstallment`, `InsurancePolicyVehicle`, `InsurancePolicyDriver`.

## Quote pipeline

- `InsuranceQuoteLead` — contact, address, coverage flags, `recommended_companies` M2M, `assigned_to` membership, `agent_task`.
- `InsuranceQuoteLeadDocument` / `Driver` / `Vehicle`
- `InsuranceQuoteDistributionConfig` — 1:1 org; auto on/off, skip Sundays, attendance required.
- `InsuranceAgentOffDay`

## Finance

- `DailyPaymentTransaction` — required client; optional policy + company; amount/method/type; `is_cleared`.
- `BankAccount` — balance mutated by `BankTransaction` save/delete.
- `BankTransaction` — income/expense; optional `insurance_company`.

Commissions live **on the policy**, not a commission table.

## Other insurance tables

- E-sign: `InsuranceESignEnvelope` (org-scoped; no client/policy FK).
- Targets: monthly / line / market-premium-assumption.
- Agent portal: `AgentTask`, `AgentAttendanceSession`, `AgentActivityEvent`.

## Not present (RegiConnect must add)

Market access, appointments, producer codes, connectors, connections, submissions, canonical quotes, binds, webhooks, SFTP jobs, ACORD maps, reconciliation, certification runs, secret references, outbox, DLQ.

Do **not** create `RegiCustomer`, `RegiDriver`, `RegiVehicle`, `RegiPolicy`, or a second quote pipeline.
