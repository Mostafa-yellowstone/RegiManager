"""Bridge: InsuranceQuoteLead (quote pipeline) -> quote engine request -> run.

Uses only data that is on the lead. Nothing is invented: a field the lead does
not have is left empty, so validation reports it as missing. Agents can pass
`extra` (same shape as the request) to fill gaps; extra wins over lead data.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .runner import RunReport, run_quotes
from .validators import has_errors, validate_quote_request

LINE_BY_TYPE = {
    "auto_personal": "auto",
    "commercial_auto": "commercial_auto",
    "trucking": "commercial_auto",
}


def _merge(base: dict, extra: dict) -> dict:
    out = deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        elif v not in (None, "", [], {}):
            out[k] = deepcopy(v)
    return out


def lead_to_request(lead, extra: dict | None = None) -> dict[str, Any]:
    parts = (lead.client_name or "").strip().split()
    first = parts[0] if parts else ""
    last = " ".join(parts[1:]) if len(parts) > 1 else ""
    lob = LINE_BY_TYPE.get((lead.insurance_type or "").strip(), (lead.insurance_type or "").strip() or "auto")
    street = " ".join(x for x in ((lead.street_address or "").strip(), (lead.apartment or "").strip()) if x)
    req: dict[str, Any] = {
        "line_of_business": lob,
        "contact": {"email": lead.email or "", "phone": lead.phone or ""},
        "garaging_address": {"street": street, "city": lead.city, "state": lead.state, "zip": lead.zip_code},
        "drivers": [{
            "first_name": first, "last_name": last,
            "date_of_birth": lead.date_of_birth.isoformat() if lead.date_of_birth else "",
            "license_number": lead.dl_number, "relationship": "self",
        }],
        "vehicles": [{
            "vin": lead.vin, "year": lead.vehicle_year, "make": lead.vehicle_make, "model": lead.vehicle_model,
            "ownership": lead.vehicle_ownership if lead.vehicle_ownership in ("owned", "financed") else "",
            "coverage": lead.coverage_type,
        }],
        "prior_insurance": {"has_prior": bool(lead.has_prior)},
    }
    if lead.has_accident:
        # The lead only says an accident exists, not when. Left dateless on purpose so validation asks for it.
        req["drivers"][0]["accidents"] = [{}]
    return _merge(req, extra or {})


def run_for_lead(lead, extra: dict | None = None, organization=None) -> RunReport:
    """Validate the lead data and, if clean, run all carriers with an enabled login."""
    from ..carrier_credentials_models import usable_carrier_keys

    req = lead_to_request(lead, extra)
    org = organization or lead.organization
    allowed = usable_carrier_keys(org, req["line_of_business"]) if req["line_of_business"] in ("auto", "commercial_auto") else set()
    return run_quotes(req, allowed_keys=allowed)


def missing_fields(lead, extra: dict | None = None) -> list[dict[str, str]]:
    """What an agent still has to fill in before the engine can run this lead."""
    return [i.as_dict() for i in validate_quote_request(lead_to_request(lead, extra)) if i.severity == "error"]
