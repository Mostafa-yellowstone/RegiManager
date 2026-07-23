# RegiManager Companion App API

Official REST reference for **mobile / desktop companion apps** (iOS, Android, React Native, Flutter, etc.) integrating with RegiManager.

| | |
|--|--|
| **Production base URL** | `https://regimanager.com` |
| **API prefix** | `/api/` |
| **Auth** | DRF Token — `Authorization: Token <key>` |
| **Format** | JSON (`Accept: application/json`, `Content-Type: application/json`) |
| **Interactive docs** | `/api/docs/swagger/` · `/api/docs/redoc/` · `/api/schema/` |

---

## Table of contents

1. [Quick start](#quick-start)
2. [Authentication](#authentication)
3. [Multi-tenant (PSB) scoping](#multi-tenant-psb-scoping)
4. [Pagination, filters, errors, rate limits](#pagination-filters-errors-rate-limits)
5. [CRM API — clients, vehicles, service records](#crm-api)
6. [Owner API — finance, spaces, processes, notifications](#owner-api)
7. [Finance domain encapsulation](#finance-domain-encapsulation)
8. [Endpoint index](#endpoint-index)
9. [App integration checklist](#app-integration-checklist)
10. [Roadmap (not in API yet)](#roadmap-not-in-api-yet)

---

## Quick start

### 1. Login

```http
POST /api/auth/login/
Content-Type: application/json

{
  "username": "agent1",
  "password": "your-password"
}
```

**`200` response:**

```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "token_type": "Token",
  "user": {
    "id": 3,
    "username": "agent1",
    "email": "agent@psb.com",
    "full_name": "Agent One"
  },
  "organizations": [
    {
      "id": 1,
      "name": "Xpress Insurance PSB",
      "city": "Buffalo",
      "state": "NY",
      "role": "owner",
      "permissions": {
        "can_view_reports": true,
        "can_view_net_profit": true,
        "can_manage_referrals": true,
        "can_trigger_automation": true,
        "can_view_banking": true,
        "can_manage_news": true,
        "can_manage_knowledge_hub": true,
        "can_manage_documents": true,
        "can_manage_email_marketing": false,
        "can_view_spaces": true,
        "can_issue_refund": true
      }
    }
  ],
  "default_organization_id": 1
}
```

### 2. Call protected endpoints

```http
GET /api/clients/
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
Accept: application/json
```

### 3. Logout (revokes all tokens for the user)

```http
POST /api/auth/logout/
Authorization: Token <token>
```

**`200`:** `{ "detail": "Signed out." }`

---

## Authentication

| Item | Detail |
|------|--------|
| Scheme | `Authorization: Token <key>` |
| Login | `POST /api/auth/login/` |
| Profile | `GET /api/auth/me/` |
| Logout | `POST /api/auth/logout/` |

### Rules for mobile

- Use **Token auth only**. Do not rely on browser session cookies.
- Token auth does **not** conflict with the web portal’s single-session rule.
- Store the token in **secure storage** (Keychain / EncryptedSharedPreferences / Keystore).
- On **`401`**, clear the token and show the login screen.
- Logout deletes **all** API tokens for that user.

### `GET /api/auth/me/`

```json
{
  "user": {
    "id": 3,
    "username": "agent1",
    "email": "agent@psb.com",
    "full_name": "Agent One"
  },
  "organizations": [ /* same membership objects as login */ ],
  "server_time": "2026-07-19T12:00:00.000000-04:00"
}
```

Does **not** return `token` or `default_organization_id`.

### Login errors

| Code | Body |
|------|------|
| `400` | `{ "detail": "username and password are required." }` |
| `401` | `{ "detail": "Invalid credentials." }` |
| `403` | `{ "detail": "No active PSB membership for this account." }` |

### Permission flags (`organizations[].permissions`)

| Flag | Typical use in app |
|------|--------------------|
| `can_view_reports` | Owner finance / BI screens |
| `can_view_net_profit` | Show net profit after referral |
| `can_view_spaces` | Spaces tab |
| `can_view_banking` | Insurance banking / clear payments (web; limited on mobile today) |
| `can_manage_referrals` | Referral management UI |
| `can_trigger_automation` | Trigger renewal scans |
| `can_issue_refund` | Refund actions |
| `can_manage_news` | Site news admin |
| `can_manage_knowledge_hub` | Knowledge hub admin |
| `can_manage_documents` | Documents space admin |
| `can_manage_email_marketing` | Email marketing |

`role` is `"owner"` or `"member"` (agent).

---

## Multi-tenant (PSB) scoping

Every user only sees data for **active organization memberships**.

### CRM endpoints (`/api/clients/`, `/api/vehicles/`, `/api/service-records/`)

- Lists return a **combined** dataset across **all** of the user’s PSBs.
- There is **no** `X-Organization-Id` filter on CRM today.
- Create attaches the user’s **first active membership org** (unordered queryset — prefer single-PSB users, or filter client-side by `organization`).
- Use `organizations` from login / `/me/` for a PSB picker in the UI.

### Owner endpoints (`/api/owner/...`)

Scope to one PSB with either:

```http
X-Organization-Id: 1
```

or:

```http
GET /api/owner/overview/?organization_id=1
```

| Behavior | Detail |
|----------|--------|
| Header or query present | Must be an org the user belongs to; else `403` |
| Omitted | Server picks one accessible org (`Organization` filter; typically first by PK) |
| Login `default_organization_id` | First org ordered by **name** — may differ from owner default if header omitted |

**Always send `X-Organization-Id` in the owner app** after the user picks a PSB.

---

## Pagination, filters, errors, rate limits

### Pagination (CRM lists)

Default page size: **20**

```http
GET /api/clients/?page=2
```

```json
{
  "count": 145,
  "next": "https://regimanager.com/api/clients/?page=3",
  "previous": "https://regimanager.com/api/clients/?page=1",
  "results": []
}
```

### Filters (exact match)

| Resource | Query params |
|----------|----------------|
| Clients | `first_name`, `last_name`, `email` |
| Vehicles | `client`, `vin`, `plate_number`, `vehicle_type` |
| Service records | `status`, `service_type`, `case_id` |

```http
GET /api/clients/?last_name=Smith&page=1
GET /api/vehicles/?client=42
GET /api/service-records/?status=completed
```

### Error shapes

| Code | Meaning |
|------|---------|
| `400` | Validation — field errors or `{ "detail": "…" }` |
| `401` | Missing / invalid token — re-login |
| `403` | No membership or feature permission |
| `404` | Not found (or not in your orgs) |
| `429` | Rate limited |
| `500` | Server error |

Field validation:

```json
{
  "first_name": ["This field is required."]
}
```

### Rate limits

| Audience | Limit |
|----------|-------|
| Anonymous (login) | 60 / minute |
| Authenticated | 600 / minute |

---

## CRM API

All require `Authorization: Token …` and `IsAuthenticated`.

### Clients — `/api/clients/`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/clients/` | List (paginated) |
| `POST` | `/api/clients/` | Create |
| `GET` | `/api/clients/{id}/` | Retrieve |
| `PUT` / `PATCH` | `/api/clients/{id}/` | Update |
| `DELETE` | `/api/clients/{id}/` | Delete |

**Fields:**

| Field | Notes |
|-------|--------|
| `id`, `created_at` | Read-only |
| `organization` | Returned on read; create forces membership org |
| `source`, `referral` | Optional |
| `first_name`, `last_name`, `middle_name` | |
| `driver_license`, `dob`, `phone_number`, `email`, `gender` | |
| Mailing address | `building_no`, `street_address`, `apartment`, `city`, `state`, `zip_code`, `county` |
| Residence address | `residence_building_no`, `residence_street_address`, `residence_apartment`, `residence_city`, `residence_zip_code`, `residence_county` |
| Commercial | `is_commercial`, `business_name`, `business_ein` |

Sensitive fields (SSN, files, soft-delete) are **not** exposed.

---

### Vehicles — `/api/vehicles/`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/vehicles/` | List |
| `POST` | `/api/vehicles/` | Create (requires `client`) |
| `GET` | `/api/vehicles/{id}/` | Retrieve |
| `PUT` / `PATCH` | `/api/vehicles/{id}/` | Update |
| `DELETE` | `/api/vehicles/{id}/` | Delete |

**Fields:** `id`, `client`, `vehicle_number`, `plate_number`, `vin`, `year`, `make`, `model`, `vehicle_type`, `body_type`, `fuel_type`, `plate_type`, `color`, `registration_expiration_date`, `insurance_expiration_date`, `is_priority`, `is_legacy_vin`, `created_at`

**Read-only:** `id`, `created_at`

---

### Service records — `/api/service-records/`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/service-records/` | List transactions |
| `POST` | `/api/service-records/` | Create (`handled_by` = current user) |
| `GET` | `/api/service-records/{id}/` | Retrieve |
| `PUT` / `PATCH` | `/api/service-records/{id}/` | Update |
| `DELETE` | `/api/service-records/{id}/` | Delete |

**Status values:** `pending` · `completed` · `failed` · `refund`

**Payment methods:** `cash` · `zelle` · `checks` · `visa` · `mastercard` · `discover` · `diners_club` · `american_express`

**Read-only on write:** `receipt_number`, `case_id`, `service_fee`, `referral_balance`, `referral_commission`, `created_at`, `updated_at`

**Writable money / ops fields (among others):** `processing_fee`, `dmv_fee`, `sales_tax`, `dmv_sales_tax`, `credit_card_fee`, `other_fees`, `other_dmv_fee`, `paid_amount`, `paid_amount_2`, `payment_method`, `payment_method_2`, `status`, `service_type`, `transaction_date`, `vehicle`, `notes`, `source`, `referral`, client snapshot fields (`client_name`, `phone_no`, …)

---

## Owner API

For **PSB owners** and agents with finance / spaces permissions. Read-only operational intelligence — not CRM data entry.

Always send:

```http
Authorization: Token <token>
X-Organization-Id: <psb_id>
```

### Permission matrix

| Endpoint group | Required |
|----------------|----------|
| Overview, finance, insurance policies, processes | Owner **or** `can_view_reports` **or** `can_view_net_profit` |
| Spaces list / detail | Owner **or** `can_view_spaces` |
| Notifications list | Owner **or** finance permission (same as overview) |
| Mark notification read | Authenticated owner of that notification row |

---

### `GET /api/owner/overview/`

Optional **custom date range** (inclusive). When both dates are present, each profit block includes a ledger-backed `custom` bucket and a top-level `range` object.

| Query | Required | Notes |
|-------|----------|-------|
| `from_date` | with `to_date` | `YYYY-MM-DD` (aliases: `start_date`, `date_from`, `start`) |
| `to_date` | with `from_date` | `YYYY-MM-DD` (aliases: `end_date`, `date_to`, `end`) |

- Invalid / inverted / >366-day ranges → **`400`**
- No dates → presets only (`today` / `month` / `year`); `custom` is zeros

```http
GET /api/owner/overview/?from_date=2026-07-10&to_date=2026-07-12
```

`combined_profit.custom` and `dmv_core.custom` / `insurance.custom` / each space `custom` are summed from ledger rows in that window (`source: "ledger"`).

Combined owner home: profit by domain + process counts (+ multi-location ranks for owners).

```json
{
  "organization": {
    "id": 1,
    "name": "Xpress Insurance PSB",
    "city": "Buffalo",
    "state": "NY"
  },
  "profit": {
    "dmv_core": {
      "today": {
        "total_records": 12,
        "total_revenue": "2400.00",
        "gross_profit": "600.00",
        "net_profit_after_referral": "520.00",
        "referral_commission": "80.00",
        "dmv_fee": "900.00",
        "sales_tax": "0.00",
        "credit_card_fee": "12.00",
        "completed": 10,
        "pending": 2,
        "failed": 0,
        "refund": 0
      },
      "month": { },
      "year": { },
      "custom": { },
      "as_of": "2026-07-19"
    },
    "insurance": {
      "today": {
        "bound_count": 2,
        "premium": "2400.00",
        "commission": "240.00",
        "broker_fee": "50.00",
        "total_profit": "290.00"
      },
      "month": { },
      "year": { },
      "custom": { },
      "pipeline": {
        "quotes": 8,
        "bound": 2,
        "conversion_pct": 25.0,
        "previous_month": {
          "quotes": 6,
          "bound": 1,
          "conversion_pct": 16.7
        }
      },
      "as_of": "2026-07-19"
    },
    "spaces": [
      {
        "key": "insurance",
        "label": "Insurance",
        "today": { "profit": "290.00", "transactions": 2 },
        "month": { "profit": "1200.00", "transactions": 18 },
        "year": { "profit": "9000.00", "transactions": 140 },
        "custom": { "profit": "0.00", "transactions": 0 }
      }
    ],
    "combined_profit": {
      "today": "890.00",
      "month": "…",
      "year": "…",
      "custom": "0.00"
    }
  },
  "processes": { },
  "locations": [
    {
      "id": 1,
      "name": "Buffalo",
      "city": "Buffalo",
      "state": "NY",
      "daily_profit": "600.00",
      "monthly_profit": "…",
      "yearly_profit": "…",
      "total_records": 12,
      "rank": 1
    }
  ]
}
```

- `locations` only appears when `role === "owner"` **and** the user has **more than one** organization.
- `combined_profit` = DMV gross + each accessible space **once**. Insurance is **not** double-counted when the insurance space is already in `spaces`.

---

### `GET /api/owner/finance/summary/`

Domain-separated finance detail (see [encapsulation](#finance-domain-encapsulation)).

```json
{
  "dmv": {
    "today": { },
    "month": { },
    "year": { },
    "as_of": "2026-07-19",
    "daily_payments": {
      "cards": [
        {
          "key": "cash",
          "label": "Cash",
          "icon": "💵",
          "gradient": "…",
          "accent": "…",
          "total": "150.00"
        },
        { "key": "zelle", "label": "Zelle", "total": "0.00" },
        { "key": "credit_card", "label": "Credit Card", "total": "80.00" },
        { "key": "checks", "label": "Checks", "total": "0.00" }
      ],
      "grand_total": "230.00"
    }
  },
  "insurance": {
    "today": { },
    "month": { },
    "year": { },
    "pipeline": { },
    "as_of": "2026-07-19",
    "daily_payments": {
      "cards": [ ],
      "grand_total": "40.00"
    }
  },
  "goal_forecast": {
    "month_label": "July 2026",
    "month_key": "2026-07",
    "days_in_month": 31,
    "days_elapsed": 19,
    "days_remaining": 12,
    "mtd_revenue": "4200.00",
    "mtd_records": 80,
    "prev_month_revenue": "6100.00",
    "suggested_goal": "6405.00",
    "daily_run_rate": "221.05",
    "projected_month_end": "6852.63",
    "required_daily_pace": "183.75",
    "pace_pct": "107.0",
    "mtd_pct": "65.6",
    "status": "on_track",
    "status_label": "On Track",
    "status_detail": "Current pace projects meeting your profit target.",
    "gap_to_goal": "-447.63"
  }
}
```

| Key | Source |
|-----|--------|
| `dmv` | Registration `ServiceRecord` profit + **DMV** daily intake cards |
| `insurance` | Bound policy commission/broker + **Insurance Space** daily payments |
| `goal_forecast` | DMV `processing_fee` month pace only |

**There is no top-level `daily_payments` key.** Use `dmv.daily_payments` and `insurance.daily_payments`.

**Custom range:** same `from_date` / `to_date` contract as overview. When set:
- `dmv.custom` / `insurance.custom` are ledger totals for the window
- `dmv.daily_payments` / `insurance.daily_payments` are **range** payment-method cards (not “today”)
- response includes `range: { from, to, source: "ledger" }`

**Daily card keys:** `cash` · `zelle` · `credit_card` · `checks`  
(DMV card brands like visa/mastercard roll up into `credit_card`.)

---

### `GET /api/owner/finance/records/`

Ledger payment rows for Finance method drill-down (companion `PaymentRecord` shape).

```http
GET /api/owner/finance/records/?category=dmv&method=cash&from_date=2026-07-10&to_date=2026-07-12
```

| Query | Required | Notes |
|-------|----------|-------|
| `category` | No | `dmv` (default) or `insurance` |
| `method` | No | `cash` · `zelle` · `card`/`credit_card` · `checks` |
| `from_date` / `to_date` | No | Inclusive ledger window (same aliases as overview). Without dates: `timeframe=daily` (today) or `monthly` (MTD). |
| `limit` | No | 1–500 (default 100) |

```json
{
  "results": [
    {
      "id": "dmv_12_cash",
      "transaction_date": "2026-07-11",
      "description": "registration",
      "method": "cash",
      "amount": "80.00",
      "client_name": "Range Cash",
      "reference": "RCPT-…"
    }
  ],
  "count": 1,
  "range": { "from": "2026-07-10", "to": "2026-07-12", "source": "ledger" }
}
```

---

### `GET /api/owner/finance/compare/`

**DMV ServiceRecord only.**

```http
GET /api/owner/finance/compare/?compare_a=2026-04&compare_b=2026-05
GET /api/owner/finance/compare/?compare_a=2026-04&compare_b=2026-05&mode=quarter
```

| Query | Required | Values |
|-------|----------|--------|
| `compare_a` | Yes | `YYYY-MM` |
| `compare_b` | Yes | `YYYY-MM` |
| `mode` | No | `month` (default) · `quarter` |

```json
{
  "mode": "month",
  "period_a": {
    "label": "April 2026",
    "stats": {
      "revenue": "…",
      "records": 40,
      "gross_profit": "…",
      "net_profit_after_referral": "…"
    }
  },
  "period_b": { },
  "deltas": {
    "revenue_pct": 12.5,
    "records_pct": 8.0,
    "gross_profit_pct": 10.2,
    "net_profit_pct": 9.1
  }
}
```

**`400`** if months missing or invalid.

---

### `GET /api/owner/finance/chart/`

**DMV only.**

```http
GET /api/owner/finance/chart/?months=12
```

`months`: 1–24 (default 12).

```json
{
  "labels": ["Aug 2025", "Sep 2025", "…"],
  "revenue": ["1200.00", "…"],
  "gross_profit": ["300.00", "…"]
}
```

---

### `GET /api/owner/spaces/`

```json
{
  "spaces": [
    {
      "id": 5,
      "key": "insurance",
      "label": "Insurance",
      "description": "Insurance CRM and Financial space",
      "profit": {
        "key": "insurance",
        "label": "Insurance",
        "today": { "profit": "290.00", "transactions": 2 },
        "month": { "profit": "1200.00", "transactions": 18 },
        "year": { "profit": "9000.00", "transactions": 140 }
      }
    }
  ]
}
```

**Default space keys:** `insurance` · `motorclub` · `custom_inventory` · `documents` · `knowledge_hub` · `tlc`

**Extra profit fields by key:**

| Key | Extra |
|-----|--------|
| `motorclub` | `active_memberships` (list); detail also adds `motorclub_summary` + `motorclub_memberships` |
| `custom_inventory` | `inventory_value`; detail also adds `inventory_summary` + `inventory_items` |
| `documents` | `total_records`; detail also adds `documents_summary` + `vault_documents` |
| `knowledge_hub` | detail adds `knowledge_summary` + `knowledge_articles` |
| `tlc` | detail adds `tlc_summary` + `tlc_policies` |

---

### `GET /api/owner/spaces/{id}/`

Same as a list item, plus:

- **`insurance`:** `pipeline` (quotes / bound / conversion)
- **`tlc`:** `tlc_summary` (policy counts + aggregate profit/revenue) and `tlc_policies` (default active slice)
- **`motorclub`:** `motorclub_summary` (active / channel / tier / revenue KPIs) and `motorclub_memberships` (latest active rows)
- **`custom_inventory`:** `inventory_summary` (stock/value/sales KPIs) and `inventory_items`
- **`documents`:** `documents_summary` (records/folders/types) and `vault_documents`
- **`knowledge_hub`:** `knowledge_summary` (materials/roadmaps) and `knowledge_articles`

**`404`:** `{ "detail": "Space not found." }`

---

### `GET /api/owner/motorclub/memberships/`

```http
GET /api/owner/motorclub/memberships/?status=active&channel=direct&limit=50
```

| Query | Values |
|-------|--------|
| `status` | `active` · `pending` · `cancelled` · `expired` |
| `channel` | `insurance_client` · `b2b` · `direct` |
| `limit` | 1–200 (default 50) |

```json
{
  "memberships": [
    {
      "id": 12,
      "membership_number": "MC-1-00012",
      "client_name": "Jane Doe",
      "status": "active",
      "channel": "direct",
      "channel_label": "Direct / Walk-In",
      "tier": 50,
      "plan_type": "$50",
      "joined_date": "2026-03-22",
      "start_date": "2026-03-22",
      "end_date": "2027-03-22",
      "provider_profit": "20.00",
      "psb_profit": "30.00",
      "added_by": "agent1",
      "b2b_partner_name": null
    }
  ],
  "as_of": "2026-07-19"
}
```

---

### `GET /api/owner/tlc/policies/`

```http
GET /api/owner/tlc/policies/?status=active&limit=50
```

| Query | Values |
|-------|--------|
| `status` | `active` · `pending` · `cancelled` · `suspended` · `expired` · `reinstated` |
| `limit` | 1–200 (default 50) |

`cancelled` includes suspended policies. Response: `{ "policies": [...], "as_of": "..." }`.

---

### `GET /api/owner/inventory/products/`

```http
GET /api/owner/inventory/products/?stock_status=low_stock&limit=50
```

| Query | Values |
|-------|--------|
| `stock_status` | `normal` · `low_stock` · `out_of_stock` |
| `limit` | 1–200 (default 50) |

Response: `{ "items": [...], "as_of": "..." }` with `item_name`, `sku`, `stock_count`, `unit_price`, `reorder_status`, `category`.

---

### `GET /api/owner/documents/records/`

```http
GET /api/owner/documents/records/?doc_type=Registration&limit=50
```

| Query | Values |
|-------|--------|
| `doc_type` | Document type name (case-insensitive) |
| `limit` | 1–200 (default 50) |

Response: `{ "documents": [...], "as_of": "..." }`.

---

### `GET /api/owner/knowledge/materials/`

```http
GET /api/owner/knowledge/materials/?roadmap=DMV%20Rules&limit=50
```

| Query | Values |
|-------|--------|
| `roadmap` | Roadmap name (case-insensitive) |
| `limit` | 1–200 (default 50) |

Response: `{ "articles": [...], "as_of": "..." }`.

---

### `GET /api/owner/insurance/policies/`

```http
GET /api/owner/insurance/policies/?stage=bound&limit=50
```

| Query | Values |
|-------|--------|
| `stage` | `quote` · `bound` · `endorsement` |
| `limit` | 1–200 (default 50) |

```json
{
  "policies": [
    {
      "id": 99,
      "policy_number": "POL-100",
      "stage": "bound",
      "status": "active",
      "client_name": "Jane Doe",
      "insurance_company": "Test Insurance Co",
      "premium": "1200.00",
      "commission_amount": "120.00",
      "broker_fee": "25.00",
      "bound_date": "2026-07-19",
      "added_by": "agent1"
    }
  ],
  "as_of": "2026-07-19"
}
```

When a policy becomes **bound**, all PSB **owners** get a notification with `event_type: "policy_bound"`.

---

### `GET /api/owner/processes/`

```json
{
  "summary": {
    "service_status": [
      { "status": "pending", "label": "Pending", "count": 3 }
    ],
    "dmv_intake": {
      "pending": 2,
      "processing": 0,
      "approved": 10,
      "rejected": 1
    },
    "insurance_intake": {
      "pending": 1,
      "approved": 4,
      "rejected": 0
    },
    "insurance_pipeline": {
      "quotes_open": 8,
      "bound_active": 40,
      "bound_inactive": 3
    },
    "as_of": "2026-07-19"
  },
  "recent_services": [
    {
      "id": 501,
      "case_id": "…",
      "service_type": "vehicle_registration",
      "status": "completed",
      "client_name": "Jane Doe",
      "processing_fee": "25.00",
      "transaction_date": "2026-07-19",
      "handled_by": "agent1"
    }
  ]
}
```

`dmv_intake` / `insurance_intake` are `{}` when that public intake portal is disabled for the org.

---

### Notifications

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/api/owner/notifications/` | List |
| `POST` | `/api/owner/notifications/{id}/read/` | Mark one read |
| `POST` | `/api/owner/notifications/mark-all-read/` | Mark **all** unread for the user (global) |

**GET query params:**

| Param | Values |
|-------|--------|
| `event_type` | e.g. `policy_bound` |
| `unread` | `1` / `true` / `yes` |
| `limit` | 1–200 (default 50) |

```json
{
  "notifications": [
    {
      "id": 12,
      "event_type": "policy_bound",
      "title": "Policy bound",
      "message": "…",
      "level": "info",
      "is_read": false,
      "created_at": "2026-07-19T15:00:00Z",
      "client_name": "Jane Doe",
      "insurance_company_id": 3,
      "insurance_company_name": "Test Insurance Co",
      "organization_id": 1,
      "policy_id": 99
    }
  ],
  "unread_count": 4
}
```

`unread_count` is the user’s **global** unread total (not limited by the current filter).

**Mark one:** `{ "detail": "Marked read." }`  
**Mark all:** `{ "detail": "Marked read.", "updated": 4 }`

---

## Finance domain encapsulation

RegiManager keeps **DMV Finance & BI** separate from **Space money**.

| Domain | Data | Owner API location |
|--------|------|--------------------|
| DMV / registration | `ServiceRecord` fees & payments | `dmv`, `dmv.daily_payments`, compare, chart, goal forecast |
| Insurance Space | Bound commissions + `DailyPaymentTransaction` | `insurance`, `insurance.daily_payments`, spaces `key=insurance` |
| TLC / motorclub / inventory | Space-local ledgers | `/api/owner/spaces/` only — **never** mixed into DMV finance endpoints |

**Do not** add `insurance.daily_payments.grand_total` into DMV intake cards in the app UI. Show two separate “today’s cash” sections (or tabs).

---

## Endpoint index

```
POST   /api/auth/login/
POST   /api/auth/logout/
GET    /api/auth/me/

GET    /api/clients/
POST   /api/clients/
GET    /api/clients/{id}/
PUT    /api/clients/{id}/
PATCH  /api/clients/{id}/
DELETE /api/clients/{id}/

GET    /api/vehicles/
POST   /api/vehicles/
GET    /api/vehicles/{id}/
PUT    /api/vehicles/{id}/
PATCH  /api/vehicles/{id}/
DELETE /api/vehicles/{id}/

GET    /api/service-records/
POST   /api/service-records/
GET    /api/service-records/{id}/
PUT    /api/service-records/{id}/
PATCH  /api/service-records/{id}/
DELETE /api/service-records/{id}/

GET    /api/owner/overview/
GET    /api/owner/finance/summary/
GET    /api/owner/finance/records/
GET    /api/owner/finance/compare/
GET    /api/owner/finance/chart/
GET    /api/owner/spaces/
GET    /api/owner/spaces/{id}/
GET    /api/owner/insurance/policies/
GET    /api/owner/motorclub/memberships/
GET    /api/owner/tlc/policies/
GET    /api/owner/inventory/products/
GET    /api/owner/documents/records/
GET    /api/owner/knowledge/materials/
GET    /api/owner/processes/
GET    /api/owner/notifications/
POST   /api/owner/notifications/{id}/read/
POST   /api/owner/notifications/mark-all-read/

GET    /api/schema/
GET    /api/docs/swagger/
GET    /api/docs/redoc/
```

### Portal-only (session / web — not primary Token companion APIs)

These require a logged-in **browser session** (`@login_required`). Prefer owner/CRM Token APIs for mobile.

| Path | Purpose |
|------|---------|
| `/api/session-heartbeat/` | Session still active |
| `/api/get-latest-news/` | Latest site news |
| `/api/mark-site-news-read/` | Mark news read |
| `/api/set-portal-timezone/` | Set portal timezone |

---

## App integration checklist

### Agent / CRM companion

1. Login → store token + `organizations` + permissions  
2. Tab shell: Clients · Vehicles · Services · More  
3. Paginated lists + pull-to-refresh  
4. Client detail → vehicles `?client={id}` → create service record  
5. Respect `401` → clear token  

### Owner companion

1. Login as owner (or finance-enabled agent)  
2. Persist selected PSB → send `X-Organization-Id` on every owner call  
3. Home: `GET /api/owner/overview/` → today/month/year cards + process badges  
4. Finance: chart + compare + summary with **split** DMV vs Insurance daily cards  
5. Spaces: list → detail (insurance pipeline / TLC summary)  
6. Poll notifications `?event_type=policy_bound&unread=1` every ~60s until push exists  

### Recommended request wrapper (JS)

```javascript
async function api(path, { method = 'GET', body, orgId, headers } = {}) {
  const token = await SecureStore.getItemAsync('api_token');
  const res = await fetch(`${BASE_URL}/api${path}`, {
    method,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Token ${token}` } : {}),
      ...(orgId ? { 'X-Organization-Id': String(orgId) } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    await SecureStore.deleteItemAsync('api_token');
    // navigate to Login
    throw new Error('Unauthorized');
  }
  if (!res.ok) throw await res.json();
  return res.status === 204 ? null : res.json();
}
```

### Security

- [ ] HTTPS only in production  
- [ ] Token only in secure storage — never logs  
- [ ] Clear token on logout / `401`  
- [ ] Gate screens with `permissions` from `/api/auth/me/`  
- [ ] Optional: certificate pinning, biometric unlock  

### Interactive OpenAPI

1. Log in on the web (or obtain a token)  
2. Open `https://regimanager.com/api/docs/swagger/`  
3. **Authorize** → `Token <your-api-token>`  

---

## Roadmap (not in API yet)

| Feature | Status |
|---------|--------|
| Login / token / CRM CRUD | **Shipped** |
| Owner overview, finance, spaces, processes, notifications | **Shipped** |
| Org header on **CRM** lists | Planned |
| Approve/reject intake from mobile | Planned |
| PDF receipts / document upload | Planned |
| Push (FCM / APNs) + `POST /api/devices/register/` | Planned |
| Online card capture / payment gateway | Not started |

---

## Support

- Swagger: `/api/docs/swagger/`  
- ReDoc: `/api/docs/redoc/`  
- OpenAPI JSON: `/api/schema/`  
- This file: `docs/COMPANION_APP_API.md`
