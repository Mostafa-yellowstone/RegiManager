# RegiManager Client Wallet API

REST API for the **end-customer mobile wallet** (Expo iOS/Android). Staff companion APIs (`/api/auth/*`, `/api/owner/*`) are separate.

| | |
|--|--|
| **Production base URL** | `https://www.regimanager.com` |
| **API prefix** | `/api/client/` |
| **Auth** | Opaque session — `Authorization: Token <client_session_token>` |
| **Format** | JSON |

Staff enable access on the client profile (**Client App Access** panel): toggle + 4–8 digit PIN. Clients log in with **org portal code** (or organization id), **phone or email**, and **PIN**. No SMS OTP in v1.

---

## Quick start

### 1. Login

```http
POST /api/client/auth/login/
Content-Type: application/json

{
  "portal_token": "<org portal code>",
  "phone": "5551234567",
  "pin": "1234",
  "device_label": "iPhone 15"
}
```

You may send `email` instead of `phone`, or `organization_id` instead of `portal_token`.

**`200` response:**

```json
{
  "token": "…",
  "client": { "id": 1, "full_name": "…", "phone_number": "…", "email": "…" },
  "organization": { "id": 1, "name": "…", "portal_token": "…" }
}
```

### 2. Authenticated calls

```http
GET /api/client/home/
Authorization: Token <token>
Accept: application/json
```

### 3. Logout

```http
POST /api/client/auth/logout/
Authorization: Token <token>
```

---

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/client/auth/login/` | No | Issue session token |
| POST | `/api/client/auth/logout/` | Yes | Revoke current session |
| GET | `/api/client/me/` | Yes | Client profile |
| GET | `/api/client/home/` | Yes | Wallet summary (next payment, totals, policies) |
| GET | `/api/client/policies/` | Yes | Policy list |
| GET | `/api/client/policies/<id>/` | Yes | Policy detail + schedule |
| GET | `/api/client/policies/<id>/schedule/` | Yes | Installments / remaining |
| GET | `/api/client/id-cards/` | Yes | Insurance ID card documents |
| GET | `/api/client/documents/` | Yes | Insurance + DMV wallet docs |
| GET | `/api/client/documents/<kind>/<id>/file/` | Yes | Download file (`kind` = `insurance` \| `dmv`) |

All data is scoped to the authenticated client.

---

## Document kinds

- **insurance** — `InsurancePolicyDocument` (DEC, ID cards, receipts, other)
- **dmv** — `ServiceDocument` types `driver_license` and `insurance_id` linked via the client’s vehicles / service records

File URLs in JSON point at the authenticated file endpoints; the app must send the `Authorization` header when fetching.

---

## Errors

| Status | Meaning |
|--------|---------|
| 400 | Missing org / phone-or-email / PIN |
| 401 | Bad credentials or missing/invalid token |
| 404 | Policy or document not found for this client |
| 429 | Login throttled (anonymous rate limit) |

---

## CRM setup

1. Open the client profile in the dashboard.
2. **Client App Access** → set a 4–8 digit PIN → enable mobile app login → Save.
3. Give the client the org **portal code** (shown truncated on the panel; full value is on the organization record) plus their phone/email and PIN.
4. Use **Revoke active app sessions** or disable access to kick devices.

---

## Mobile app

See [`client-app/README.md`](../client-app/README.md) for the Expo (iOS + Android) wallet.
