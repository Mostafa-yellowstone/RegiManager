"""Quote engine page for one pipeline lead: fill the missing details, run, see results."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .http import deny_access
from .insurance_quote_permissions import can_edit_quote_lead, membership_for_org
from .insurance_quote_pipeline_models import InsuranceQuoteLead
from .insurance_quote_pipeline_views import _active_org
from .quote_followup_models import STEP_KEYS, mark_step
from .insurance_quote_pipeline_models import BODILY_INJURY_LIMITS, DEFAULT_BODILY_INJURY
from .quote_engine.lead_bridge import (
    FLAT_FIELDS,
    default_effective_date,
    file_results_to_pipeline,
    flat_to_extra,
    lead_to_request,
    run_for_lead,
)
from .quote_engine.validators import validate_quote_request


def _parse_iso_date(raw: str):
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@login_required
@require_http_methods(["GET", "POST"])
def quote_engine_page(request, lead_id: int):
    org = _active_org(request)
    if org is None:
        deny_access("Organization required.")
    lead = get_object_or_404(InsuranceQuoteLead, id=lead_id, organization=org)
    if not can_edit_quote_lead(request.user, lead, membership=membership_for_org(request.user, org)):
        deny_access("You cannot run quotes for this lead.")

    report = None
    if request.method == "POST" and request.POST.get("action") == "step":
        key, status = request.POST.get("key", ""), request.POST.get("status", "")
        if key in STEP_KEYS and status in ("done", "pending", "blocked", "skipped"):
            try:
                mark_step(lead, key, status, user=request.user, note=(request.POST.get("note") or "").strip())
            except ValueError as exc:
                messages.error(request, str(exc))
        return redirect(reverse("quote-engine-lead", args=[lead.id]))
    if request.method == "POST":
        flat = {k: (request.POST.get(k) or "").strip() for k in FLAT_FIELDS}
        lead.quote_details = flat
        parsed_effective = _parse_iso_date(flat.get("effective_date"))
        if parsed_effective:
            lead.effective_date = parsed_effective
        if flat.get("bodily_injury_limit") in BODILY_INJURY_LIMITS:
            lead.bodily_injury_limit = flat["bodily_injury_limit"]
        lead.save(update_fields=["quote_details", "effective_date", "bodily_injury_limit", "updated_at"])
        if request.POST.get("action") == "run":
            report = run_for_lead(lead, flat_to_extra(flat), user=request.user, save=True,
                                  spend_approved=request.POST.get("spend_approved") == "1")
            if not report.blocked:
                n = file_results_to_pipeline(lead, report, user=request.user)
                if n:
                    messages.success(request, f"{n} quote{'s' if n != 1 else ''} added to this lead in the pipeline.")
            if report.blocked and request.headers.get("X-Requested-With") != "quote-engine":
                messages.error(request, "Fix the items below, then run again. Nothing was sent to any carrier.")
        else:
            messages.success(request, "Details saved.")
            return redirect(reverse("quote-engine-lead", args=[lead.id]))
    flat = {k: (lead.quote_details or {}).get(k, "") for k in FLAT_FIELDS}
    if not flat.get("effective_date") and lead.effective_date:
        flat["effective_date"] = lead.effective_date.isoformat()
    if not flat.get("bodily_injury_limit"):
        flat["bodily_injury_limit"] = lead.bodily_injury_limit or DEFAULT_BODILY_INJURY
    if not flat.get("effective_date"):
        flat["effective_date"] = default_effective_date().isoformat()
    if not flat.get("license_state"):
        flat["license_state"] = (lead.state or "NY").upper()
    if report is None:
        latest = lead.engine_runs.exclude(results=[]).first()
        if latest is not None:
            report = SimpleNamespace(blocked=False, results=latest.results)
    issues = report.issues if report and hasattr(report, "issues") else validate_quote_request(lead_to_request(lead, flat_to_extra(flat)))
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity != "error"]
    line = lead_to_request(lead, flat_to_extra(flat))["line_of_business"]
    return render(request, "core/insurance_quote_engine.html", {
        "lead": lead, "flat": flat, "errors": errors, "warnings": warnings, "report": report,
        "is_commercial": line == "commercial_auto", "line": line,
        "ready": not errors, "past_runs": lead.engine_runs.all()[:5],
        "documents": lead.documents.all(),
        "bi_limits": BODILY_INJURY_LIMITS,
        "extra_vehicles": lead.additional_vehicles.all(),
        "insurance_space": True,
    })
