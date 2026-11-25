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
    for d in lead.additional_drivers.all():
        dp = (d.full_name or "").strip().split()
        req["drivers"].append({
            "first_name": dp[0] if dp else "", "last_name": " ".join(dp[1:]),
            "date_of_birth": d.date_of_birth.isoformat() if d.date_of_birth else "",
            "license_number": d.dl_number, "relationship": "other",
        })
    for v in lead.additional_vehicles.all():
        req["vehicles"].append({"vin": v.vin, "year": v.year, "make": v.make, "model": v.model,
                                "ownership": req["vehicles"][0]["ownership"], "coverage": lead.coverage_type})
    if lead.has_accident:
        # The lead only says an accident exists, not when. Left dateless on purpose so validation asks for it.
        req["drivers"][0]["accidents"] = [{}]
    extra = dict(extra or {})
    lic_state = extra.pop("_license_state", "")
    acc_dates = extra.pop("_accident_dates", [])
    if lic_state:
        req["drivers"][0]["license_state"] = lic_state
    if acc_dates:
        req["drivers"][0]["accidents"] = [{"date": d} for d in acc_dates]
    merged = _merge(req, extra)
    # Vehicle-level commercial fields from the form apply to every vehicle.
    for k, v in (extra or {}).get("_vehicle_all", {}).items():
        for veh in merged["vehicles"]:
            veh[k] = v
    merged.pop("_vehicle_all", None)
    return merged


def run_for_lead(lead, extra: dict | None = None, organization=None, user=None, save: bool = False,
                 spend_approved: bool = False) -> RunReport:
    """Validate the lead data and, if clean, run all carriers with an enabled login."""
    from ..carrier_credentials_models import carrier_otp_emails, usable_carrier_keys

    req = lead_to_request(lead, extra)
    org = organization or lead.organization
    allowed = usable_carrier_keys(org, req["line_of_business"]) if req["line_of_business"] in ("auto", "commercial_auto") else set()
    lob = req["line_of_business"]
    emails = carrier_otp_emails(org, lob) if lob in ("auto", "commercial_auto") else {}
    from ..quote_followup_models import mark_step

    if spend_approved and save and user is not None:
        # The modal approval covers the money step and the customer-consent attestation. Recorded with who and when.
        for k in ("data_entry", "consent"):
            try:
                mark_step(lead, k, "done", user=user, note="Approved at run (MVR/POS fees, customer consent)")
            except ValueError:
                pass
    report = run_quotes(req, allowed_keys=allowed, carrier_emails=emails, spend_approved=spend_approved)
    if save:
        if not report.blocked:
            try:
                mark_step(lead, "data_entry", "done", note="Validated by quote engine", system=True)
            except ValueError:
                pass
    if save:
        from ..quote_engine_models import QuoteEngineRun
        QuoteEngineRun.objects.create(
            lead=lead, created_by=user, line_of_business=lob, blocked=report.blocked,
            issues=[i.as_dict() for i in report.issues],
            results=[{"carrier": r.carrier, "status": r.status, "premium_monthly": r.premium_monthly,
                      "premium_term": r.premium_term, "term_months": r.term_months, "detail": r.detail,
                      "quote_ref": r.quote_ref} for r in report.results],
        )
    return report


def missing_fields(lead, extra: dict | None = None) -> list[dict[str, str]]:
    """What an agent still has to fill in before the engine can run this lead."""
    return [i.as_dict() for i in validate_quote_request(lead_to_request(lead, extra)) if i.severity == "error"]


FLAT_FIELDS = (
    "effective_date", "bodily_injury_limit", "csl_limit", "license_state", "prior_carrier",
    "prior_expiration", "months_with_carrier", "accident_dates",
    "legal_name", "entity_type", "fein", "usdot", "years_in_business", "operation_type",
    "vehicle_class", "gvw", "radius_miles",
)


def flat_to_extra(flat: dict) -> dict:
    """Turn the flat quote-details form into the nested `extra` the engine understands. Blank = not provided."""
    g = lambda k: (str(flat.get(k) or "")).strip()
    ex: dict[str, Any] = {}
    for k in ("effective_date", "bodily_injury_limit"):
        if g(k):
            ex[k] = g(k)
    if g("csl_limit"):
        digits = "".join(ch for ch in g("csl_limit") if ch.isdigit())
        ex["csl_limit"] = int(digits) if digits else g("csl_limit")
    if g("prior_carrier") or g("prior_expiration"):
        ex["prior_insurance"] = {"has_prior": True, "carrier": g("prior_carrier"),
                                 "expiration_date": g("prior_expiration"),
                                 "months_with_carrier": g("months_with_carrier") or 0}
    biz = {k: g(k) for k in ("legal_name", "entity_type", "fein", "usdot", "years_in_business", "operation_type") if g(k)}
    if biz:
        ex["business"] = biz
    vall = {k: g(k) for k in ("vehicle_class", "gvw", "radius_miles") if g(k)}
    if vall:
        ex["_vehicle_all"] = vall
    if g("license_state"):
        ex["_license_state"] = g("license_state").upper()
    dates = [d.strip() for d in g("accident_dates").replace(",", "\n").splitlines() if d.strip()]
    if dates:
        ex["_accident_dates"] = dates
    return ex


def file_results_to_pipeline(lead, report: RunReport, user=None) -> int:
    """Put every quoted result on the lead as a normal quote option (the pipeline desk's own records).

    Idempotent: the same carrier, premium and quote reference is not added twice. Moves the lead to
    "quoted" only if it was still new, assigned or quoting. Returns how many options were added.
    """
    from decimal import Decimal

    from ..insurance_desk_models import InsuranceQuoteOption
    from ..insurance_quote_pipeline_models import InsuranceQuoteLead
    from ..models import InsuranceCompany

    added = 0
    from ..quote_followup_models import mark_step

    for r in report.results:
        if r.status != "quoted" or not r.premium_term:
            continue
        note = f"Quote engine{(' ref ' + r.quote_ref) if r.quote_ref else ''}"[:500]
        term = Decimal(str(r.premium_term)).quantize(Decimal("0.01"))
        if InsuranceQuoteOption.objects.filter(lead=lead, carrier_name=r.carrier, term_premium=term, note=note).exists():
            continue
        company = InsuranceCompany.objects.filter(organization=lead.organization, name__iexact=r.carrier).first()
        InsuranceQuoteOption.objects.create(
            lead=lead, company=company, carrier_name=r.carrier[:120], term_premium=term,
            term_months=r.term_months or 6, note=note, created_by=user,
        )
        added += 1
    if added and lead.stage in (InsuranceQuoteLead.Stage.NEW, InsuranceQuoteLead.Stage.ASSIGNED, InsuranceQuoteLead.Stage.QUOTING):
        lead.stage = InsuranceQuoteLead.Stage.QUOTED
        lead.save(update_fields=["stage", "updated_at"])
    if added:
        try:
            mark_step(lead, "run_quote", "done", note=f"{added} quote(s) returned", system=True)
        except ValueError:
            pass  # earlier step (e.g. consent) not done yet; leave it for the agent
    return added
