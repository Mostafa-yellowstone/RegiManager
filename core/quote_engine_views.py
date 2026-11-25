"""Quote engine page for one pipeline lead: fill the missing details, run, see results."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .http import deny_access
from .insurance_quote_permissions import can_edit_quote_lead, membership_for_org
from .insurance_quote_pipeline_models import InsuranceQuoteLead
from .insurance_quote_pipeline_views import _active_org
from .quote_followup_models import STEP_KEYS, QuoteFollowUpStep, ensure_steps, mark_step
from .quote_engine.lead_bridge import FLAT_FIELDS, file_results_to_pipeline, flat_to_extra, lead_to_request, run_for_lead
from .quote_engine.validators import Issue, validate_quote_request


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
        lead.save(update_fields=["quote_details", "updated_at"])
        if request.POST.get("action") == "run":
            report = run_for_lead(lead, flat_to_extra(flat), user=request.user, save=True)
            if not report.blocked:
                n = file_results_to_pipeline(lead, report, user=request.user)
                if n:
                    messages.success(request, f"{n} quote{'s' if n != 1 else ''} added to this lead in the pipeline.")
            if report.blocked:
                messages.error(request, "Fix the items below, then run again. Nothing was sent to any carrier.")
        else:
            messages.success(request, "Details saved.")
            return redirect(reverse("quote-engine-lead", args=[lead.id]))
    flat = {k: (lead.quote_details or {}).get(k, "") for k in FLAT_FIELDS}
    issues = report.issues if report else validate_quote_request(lead_to_request(lead, flat_to_extra(flat)))
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity != "error"]
    line = lead_to_request(lead, flat_to_extra(flat))["line_of_business"]
    return render(request, "core/insurance_quote_engine.html", {
        "lead": lead, "flat": flat, "errors": errors, "warnings": warnings, "report": report,
        "is_commercial": line == "commercial_auto", "line": line,
        "ready": not errors, "steps": ensure_steps(lead),
        "next_step": next((s for s in ensure_steps(lead) if s.status in ("pending", "blocked")), None), "past_runs": lead.engine_runs.all()[:5],
        "insurance_space": True,
    })
