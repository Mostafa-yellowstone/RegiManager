# RegiManager Companion App API

Official API reference for building a **mobile companion app** (iOS, Android, React Native, Flutter) against RegiManager.

**Production base URL:** `https://regimanager.com`  
**API prefix:** `/api/`

---

## Quick start

### 1. Login and get a token

```http
POST /api/auth/login/
Content-Type: application/json

{
  "username": "agent1",
  "password": "your-password"
}
```

**Response `200`:**

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
      "role": "member",
      "permissions": {
        "can_view_reports": true,
        "can_manage_email_marketing": false
      }
    }
  ],
  "default_organization_id": 1
}
```

### 2. Authenticated requests

```http
GET /api/clients/
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
Accept: application/json
```

### 3. Sign out (revoke token)

```http
POST /api/auth/logout/
Authorization: Token <token>
```

---

## Authentication

| Method | Details |
|--------|---------|
| **Type** | DRF Token (`Authorization: Token <key>`) |
| **Login** | `POST /api/auth/login/` |
| **Profile** | `GET /api/auth/me/` |
| **Logout** | `POST /api/auth/logout/` |

**Important for mobile:**

- Use **Token auth only**. Do not rely on browser session cookies.
- Token auth does not conflict with the web portal’s single-session rule.
- Store the token in the device **secure storage** (Keychain / EncryptedSharedPreferences).
- On `401`, clear token and show login screen.

---

## Rate limits

| Audience | Limit |
|----------|-------|
| Anonymous (login) | 60 requests / minute |
| Authenticated user | 600 requests / minute |

Exceeded limits return `429 Too Many Requests`.

---

## Multi-tenant data access

Every authenticated user only sees data for **PSB organizations they belong to** (active membership).

- List endpoints automatically filter by the user’s organization IDs.
- Create endpoints attach the user’s **first active organization** (by name order).
- Users in multiple PSBs see a **combined** dataset across all their orgs.

Use `organizations` from `/api/auth/me/` to show a PSB picker in the app UI.  
(Server-side filter by single org via header is planned for a future release.)

---

## Pagination

All list endpoints use **page number pagination**:

```http
GET /api/clients/?page=2
```

**Default page size:** 20

**Response shape:**

```json
{
  "count": 145,
  "next": "https://regimanager.com/api/clients/?page=3",
  "previous": "https://regimanager.com/api/clients/?page=1",
  "results": [ ... ]
}
```

---

## Filtering

Query parameters use exact match (django-filter):

| Resource | Filters |
|----------|---------|
| Clients | `first_name`, `last_name`, `email` |
| Vehicles | `vin`, `plate_number`, `vehicle_type` |
| Service records | `status`, `service_type`, `case_id` |

Example:

```http
GET /api/clients/?last_name=Smith&page=1
GET /api/vehicles/?vin=1HGCM82633A123456
GET /api/service-records/?status=completed&service_type=registration
```

---

## REST resources (CRUD)

### Clients — `/api/clients/`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/clients/` | List clients |
| POST | `/api/clients/` | Create client |
| GET | `/api/clients/{id}/` | Retrieve |
| PUT/PATCH | `/api/clients/{id}/` | Update |
| DELETE | `/api/clients/{id}/` | Delete |

**Writable fields:** `source`, `referral`, `first_name`, `last_name`, `middle_name`, `driver_license`, `dob`, `phone_number`, address fields, `email`, `gender`, `is_commercial`, `business_name`, `business_ein`

**Read-only:** `id`, `organization`, `created_at`

---

### Vehicles — `/api/vehicles/`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/vehicles/` | List vehicles |
| POST | `/api/vehicles/` | Create (requires `client` id) |
| GET | `/api/vehicles/{id}/` | Retrieve |
| PUT/PATCH | `/api/vehicles/{id}/` | Update |
| DELETE | `/api/vehicles/{id}/` | Delete |

**Key fields:** `client`, `vin`, `plate_number`, `year`, `make`, `model`, `vehicle_type`, `registration_expiration_date`, `insurance_expiration_date`

---

### Service records — `/api/service-records/`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/service-records/` | List transactions |
| POST | `/api/service-records/` | Create (sets `handled_by` to current user) |
| GET | `/api/service-records/{id}/` | Retrieve |
| PUT/PATCH | `/api/service-records/{id}/` | Update |
| DELETE | `/api/service-records/{id}/` | Delete |

**Read-only on create/update:** `receipt_number`, `case_id`, `service_fee`, `referral_balance`, `referral_commission`, timestamps

---

## Auxiliary JSON endpoints

These use session auth today; from mobile, send the **Token** header (they accept JSON when `Accept: application/json`).

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/auth/me/` | GET | Profile + organizations |
| `/api/session-heartbeat/` | GET | Session still valid `{ "status": "active" }` |
| `/api/get-latest-news/` | GET | Latest unread site news |
| `/api/mark-site-news-read/` | POST | Mark news read (`news_id` or `mark_all=1`) |
| `/api/set-portal-timezone/` | POST | JSON body `{ "timezone": "America/New_York" }` |

---

## Error responses

| Code | Meaning |
|------|---------|
| 400 | Validation error — check response body |
| 401 | Missing/invalid token — re-login |
| 403 | No permission or no active PSB membership |
| 404 | Object not found (or not in your orgs) |
| 429 | Rate limited |
| 500 | Server error |

DRF validation errors:

```json
{
  "field_name": ["This field is required."]
}
```

---

## OpenAPI / Swagger (interactive docs)

| URL | Access |
|-----|--------|
| `/api/schema/` | OpenAPI 3 JSON (login required) |
| `/api/docs/swagger/` | Swagger UI |
| `/api/docs/redoc/` | ReDoc UI |

Authenticate in Swagger: **Authorize** → `Token <your-api-token>`.

---

## Companion app implementation strategy

### Phase 1 — Foundation (week 1–2)

**Goal:** Login, secure token storage, org picker, basic lists.

1. **Auth module**
   - Login screen → `POST /api/auth/login/`
   - Secure token storage
   - Auto-attach `Authorization` header on every request
   - `GET /api/auth/me/` on app launch to refresh permissions
   - Logout → `POST /api/auth/logout/`

2. **Navigation shell**
   - Tab bar: Clients | Vehicles | Services | More
   - Show current PSB name from `organizations[0]` (multi-PSB picker later)

3. **Read-only lists**
   - Paginated lists with pull-to-refresh
   - Search via filter query params

**Tech stack suggestions:**

| Layer | Option A | Option B |
|-------|----------|----------|
| Mobile | React Native + Expo | Flutter |
| HTTP | Axios / fetch wrapper | Dio |
| State | TanStack Query | Riverpod |
| Auth storage | expo-secure-store | flutter_secure_storage |

---

### Phase 2 — Core CRM (week 3–4)

**Goal:** Full client + vehicle workflow.

1. Client detail screen (GET `/api/clients/{id}/`)
2. Create/edit client (POST/PATCH)
3. Vehicle list per client (`GET /api/vehicles/?client=<id>` — filter by client if exposed; otherwise filter client-side)
4. Add vehicle form
5. Offline-friendly: cache last page of lists locally (SQLite / AsyncStorage)

---

### Phase 3 — Service desk (week 5–6)

**Goal:** Agents create and track transactions from the field.

1. Service record list with status filters
2. Create service record linked to vehicle
3. Receipt/case ID display (read-only fields from API)
4. Push notification placeholder for status changes (requires future webhook/FCM API)

---

### Phase 4 — Extended portal features (requires new API endpoints)

These **are not in the API yet** — plan server work in parallel:

| Feature | Suggested endpoint |
|---------|-------------------|
| Dashboard KPIs | `GET /api/dashboard/summary/` |
| Document upload | `POST /api/services/{id}/documents/` |
| PDF receipt | `GET /api/services/{id}/receipt.pdf` |
| Intake queue | `GET /api/intake/pending/` |
| Email marketing | `GET /api/email-marketing/lists/` |
| Notifications | `GET /api/notifications/` |
| Org switch | Header `X-Organization-Id` on all requests |

Build the mobile UI against **mock data** until endpoints exist, then swap base paths.

---

### Architecture diagram

```
┌─────────────────┐
│  Companion App  │
│  (iOS/Android)  │
└────────┬────────┘
         │ HTTPS + Token Auth
         ▼
┌─────────────────┐
│  Nginx          │
└────────┬────────┘
         ▼
┌─────────────────┐     ┌──────────┐
│  Django REST    │────▶│ Postgres │
│  /api/*         │     └──────────┘
└─────────────────┘
```

---

### Security checklist

- [ ] HTTPS only in production
- [ ] Token in secure storage, never in logs
- [ ] Certificate pinning (optional, recommended for production)
- [ ] Biometric unlock for app reopen
- [ ] Clear token on logout / 401
- [ ] Respect `permissions` flags from `/api/auth/me/` before showing features

---

### Recommended request wrapper (pseudo-code)

```javascript
async function api(path, options = {}) {
  const token = await SecureStore.getItemAsync('api_token');
  const res = await fetch(`${BASE_URL}/api${path}`, {
    ...options,
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Token ${token}` } : {}),
      ...options.headers,
    },
  });
  if (res.status === 401) {
    await SecureStore.deleteItemAsync('api_token');
    navigation.navigate('Login');
    throw new Error('Unauthorized');
  }
  if (!res.ok) throw await res.json();
  return res.status === 204 ? null : res.json();
}
```

---

## Owner companion app (finance, spaces, processes)

These endpoints are for **PSB owners** (and agents with finance permissions) to track profit, spaces, insurance binding, and operational queues — **not CRM data entry**.

Pass optional header to scope one PSB:

```http
X-Organization-Id: 1
```

### Owner dashboard overview

```http
GET /api/owner/overview/
Authorization: Token <token>
```

Returns profit broken out by domain (not a mixed DMV+Spaces ledger):
- **DMV core** — today / month / year (gross + net after referral). Registration `ServiceRecord` only.
- **Insurance** — bound policy commission + broker fees (detail; also appears under spaces when accessible)
- **All spaces** — insurance, motor club, inventory, documents, TLC, etc.
- **Combined system profit** — DMV + each space once (insurance is not double-counted)
- **Process counts** — service status, DMV intake, insurance intake, open quotes

### Finance detail

| Endpoint | Purpose |
|----------|---------|
| `GET /api/owner/finance/summary/` | Domain-separated: `dmv` (registration profit + DMV daily intake), `insurance` (policy profit + Insurance Space daily payments), `goal_forecast` (DMV month goal) |
| `GET /api/owner/finance/compare/?compare_a=2026-04&compare_b=2026-05` | Month-over-month revenue, profit, record deltas (**DMV ServiceRecord only**) |
| `GET /api/owner/finance/compare/?compare_a=2026-04&compare_b=2026-05&mode=quarter` | Quarter comparison (**DMV only**) |
| `GET /api/owner/finance/chart/?months=12` | 12-month revenue + gross profit chart series (**DMV only**) |

**Encapsulation:** Web Finance Hub and DMV owner finance fields never include Insurance `DailyPaymentTransaction` or other Space ledgers. Insurance daily payments live under `insurance.daily_payments` (and in Spaces → Insurance in the web app).

**Profit fields explained:**
- `gross_profit` — sum of `processing_fee` (DMV) or commission+broker (insurance)
- `net_profit_after_referral` — DMV gross minus referral commission share

### Spaces

| Endpoint | Purpose |
|----------|---------|
| `GET /api/owner/spaces/` | All accessible spaces with today/month/year profit |
| `GET /api/owner/spaces/{id}/` | Single space detail + insurance pipeline (if insurance space) |

Space keys: `insurance`, `motorclub`, `custom_inventory`, `documents`, `knowledge_hub`

### Insurance policies & binding alerts

| Endpoint | Purpose |
|----------|---------|
| `GET /api/owner/insurance/policies/?stage=bound&limit=50` | Recent policies list |
| `GET /api/owner/notifications/?event_type=policy_bound` | Alerts when a policy is bound |
| `POST /api/owner/notifications/{id}/read/` | Mark one notification read |
| `POST /api/owner/notifications/mark-all-read/` | Mark all read |

When any policy transitions to **bound**, all PSB owners receive a notification with `event_type: "policy_bound"`.

### Process tracking

```http
GET /api/owner/processes/
```

Returns intake queue counts, insurance pipeline stats, service status breakdown, and 10 most recent service records.

### Owner app implementation strategy

**Phase 1 — Owner home screen**
1. Login as owner → store token
2. `GET /api/owner/overview/` — show combined profit cards (today / month / year)
3. Poll `GET /api/owner/notifications/?event_type=policy_bound&unread=1` every 60s (or use push later)

**Phase 2 — Finance deep dive**
1. Month comparison chart from `/api/owner/finance/chart/`
2. Compare picker → `/api/owner/finance/compare/`
3. Daily cash intake cards from `/api/owner/finance/summary/` (`dmv.daily_payments` vs `insurance.daily_payments`)

**Phase 3 — Spaces profit**
1. Spaces tab from `/api/owner/spaces/`
2. Tap space → `/api/owner/spaces/{id}/`
3. Show insurance bound count vs quotes

**Phase 4 — Process monitor**
1. Processes tab from `/api/owner/processes/`
2. Badges for pending DMV intake + insurance intake
3. Tap through to web portal for actions (approve intake) until mobile actions are added

**Phase 5 — Push notifications (future)**
- Wire FCM/APNs to backend events (`policy_bound`, intake pending, service refund)
- Requires new `POST /api/devices/register/` endpoint

### Owner permissions

| Access | Required |
|--------|----------|
| Overview, finance, insurance policies | Owner **or** `can_view_reports` **or** `can_view_net_profit` |
| Spaces list | Owner **or** `can_view_spaces` |
| Notifications | Owner **or** finance permission |

---

## What exists today vs roadmap

| Area | API today | Roadmap |
|------|-----------|---------|
| Login / token | Yes | — |
| Owner overview (profit + spaces) | Yes | Push notifications |
| Finance compare / chart | Yes | PDF report download |
| Policy bound notifications | Yes | FCM/APNs push |
| Spaces profit by period | Yes | Per-space drill-down actions |
| Process queues | Yes (counts) | Approve/reject from mobile |
| Clients CRUD | Yes | Search improvements |
| Vehicles CRUD | Yes | Link filters |
| Service records CRUD | Yes | Payments split |
| Dashboard | No | Phase 4 |
| Documents / PDFs | No | Phase 4 |
| Insurance / Spaces | No | Phase 4+ |
| Push notifications | No | FCM + backend events |

---

## Support

- Interactive docs: `/api/docs/swagger/` (after login on server)
- OpenAPI schema: `/api/schema/`
- Server must have `DB_NAME`, Redis, and email env configured for production
