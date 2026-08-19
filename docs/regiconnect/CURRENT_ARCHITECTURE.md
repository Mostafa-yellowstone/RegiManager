# Current architecture

Inspected: RegiManager Django monolith (`core` + `RegiManager` project). Pulse is out of scope.

## Shape

RegiManager is a **modular monolith**, not a set of microservices. One Django app (`core`) owns PSB operations, Insurance Space, TLC, Motor Club, inventory, documents, email marketing, and the agent portal.

- **Runtime:** Django 6, gunicorn (gevent) behind nginx on a VPS.
- **UI:** Server-rendered templates (`templates/core/`), not a SPA. Insurance Space is `templates/core/insurance_space.html`.
- **API:** Hybrid — three DRF viewsets (`Client`, `Vehicle`, `ServiceRecord`) plus many DRF `APIView`s under `/api/owner/` and `/api/agent/`, plus dashboard function views returning HTML or `JsonResponse`.
- **Auth:** Django session cookies for the dashboard; DRF `TokenAuthentication` for companion apps. No JWT.
- **Tenant:** `Organization` (verbose name PSB). Users join via `OrganizationMembership`.

## Request path

```
Browser / companion
  → nginx (static/media, proxy)
  → gunicorn WSGI
  → Django URLconf (RegiManager/urls.py)
  → core views
  → Postgres (prod) or SQLite (local)
```

Background: Celery workers consume Redis. Beat runs a small settings dict (registration reminders, license alerts, TLC installments). Email marketing already queues Celery with a sync/thread fallback when workers are absent.

## What Insurance Space is

A `Space` row with `key="insurance"`. Access: `can_view_spaces` plus that space in `accessible_spaces` (`core/space_access.py`). Opening the card does not by itself grant policy work; that uses `can_deal_with_insurance` (and `can_view_banking` for Companies/Finance).

There is **no** real carrier rating API. EZLynx is an org URL field only. DEC import is a PDF parser. E-sign is first-party PDF overlay. `regiconnect` is a connectivity + single-market mock quote path, not a comparative rater.

## Non-goals of this document

This file describes **what ships today**. Target RegiConnect design lives in `REGI_CONNECT_ARCHITECTURE.md`.
