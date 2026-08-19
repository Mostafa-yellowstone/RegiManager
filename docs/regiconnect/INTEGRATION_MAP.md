# Integration map

## Real outbound/inbound today

| System | How |
|---|---|
| SMTP | Reminders, marketing, e-sign request mail, TLC reminders |
| OCR.space | `OCR_API_KEY` + `core/ocr_service.py` |
| NHTSA vPIC | VIN decode AJAX |
| Celery/Redis | Jobs + portal fan-out |

## Config-only or in-house (not carrier APIs)

| System | Reality |
|---|---|
| EZLynx / AgentInsure | `Organization.insurance_ezlynx_quote_url` + portal mode enum. No SDK, no iframe usage in templates beyond storing the URL. |
| DEC import | `insurance_dec_import.py` / TLC variant — parse uploaded PDF text. |
| E-sign | First-party envelopes and PDF overlay. Not DocuSign. |
| Mobile push | Device tokens stored; no FCM/APNs send. |
| Payments | Cash/Zelle/card/check **recorded**, not charged via Stripe. |

## Absent (must not be faked)

- Carrier REST/SOAP **rating** or bind APIs (RegiConnect mock is not a rating source)
- EZLynx rating API (URL embed only)
- NYAIP electronic application / assignment API
- Inbound carrier webhooks used for rating
- IVANS / licensed comparative rater SDK
- Plaid / bank sync
- Twilio SMS (TLC comments “not configured”)

## Rule for Phase 7+

A connector may call a real network endpoint **only** when official documentation and authorization are in hand. Until then: **mock connector** for tests, and **skeleton connectors** that raise `MissingCarrierSpec` rather than guessed URLs.
