"""Quote engine page for one pipeline lead: fill the missing details, run, see results."""
from __future__ import annotations

import threading

from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .http import deny_access
from .insurance_quote_permissions import can_edit_quote_lead, membership_for_org
from .insurance_quote_pipeline_models import InsuranceQuoteLead
from .insurance_quote_pipeline_views import _active_org
from .quote_followup_models import STEP_KEYS, QuoteFollowUpStep, ensure_steps, mark_step
from .quote_engine.lead_bridge import FLAT_FIELDS, file_results_to_pipeline, flat_to_extra, lead_to_request, run_for_lead, run_job
from .quote_engine.validators import Issue, validate_quote_request


def start_job(job_id: int, extra: dict) -> None:
    """Runs in a background thread so the page returns at once and the modal can ask for the login code."""
    threading.Thread(target=run_job, args=(job_id, extra), daemon=True).start()


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
        if request.POST.get("action") == "run" and not [i for i in validate_quote_request(lead_to_request(lead, flat_to_extra(flat))) if i.severity == "error"]:
            from .quote_engine_models import QuoteEngineJob
            from .carrier_credentials_models import CarrierCredential

            line_ = lead_to_request(lead, flat_to_extra(flat))["line_of_business"]
            cred = CarrierCredential.objects.filter(organization=org, line=line_, enabled=True, carrier_key="progressive").first()
            job = QuoteEngineJob.objects.create(lead=lead, created_by=request.user, spend_approved=request.POST.get("spend_approved") == "1",
                                                otp_carrier="Progressive" if cred else "", otp_hint_email=(cred.otp_email if cred else ""))
            extra_ = flat_to_extra(flat)
            start_job(job.id, extra_)
            return redirect(reverse("quote-engine-lead", args=[lead.id]) + f"?job={job.id}")
        if request.POST.get("action") == "run":
            report = run_for_lead(lead, flat_to_extra(flat), user=request.user, save=True,
                                  spend_approved=request.POST.get("spend_approved") == "1")
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
        "insurance_space": True, "job_id": request.GET.get("job", ""),
    })


def _job_for(request, lead_id: int, job_id: int):
    from .quote_engine_models import QuoteEngineJob

    org = _active_org(request)
    if org is None:
        deny_access("Organization required.")
    lead = get_object_or_404(InsuranceQuoteLead, id=lead_id, organization=org)
    if not can_edit_quote_lead(request.user, lead, membership=membership_for_org(request.user, org)):
        deny_access("You cannot run quotes for this lead.")
    return get_object_or_404(QuoteEngineJob, id=job_id, lead=lead)


@login_required
@require_http_methods(["GET"])
def quote_engine_job_status(request, lead_id: int, job_id: int):
    job = _job_for(request, lead_id, job_id)
    out = {"status": job.status, "message": job.message, "carrier": job.otp_carrier, "email": job.otp_hint_email}
    if job.status == "done" and job.run:
        out["results"] = [{"carrier": r["carrier"], "status": r["status"], "premium_term": r.get("premium_term"), "detail": r.get("detail", "")}
                          for r in job.run.results]
        out["issues"] = [i.get("message", "") for i in job.run.issues]
    return JsonResponse(out)


@login_required
@require_http_methods(["POST"])
def quote_engine_job_otp(request, lead_id: int, job_id: int):
    from .carrier_credentials_models import encrypt_secret
    from .quote_engine_models import QuoteEngineJob

    job = _job_for(request, lead_id, job_id)
    if job.status != "waiting_otp":
        return JsonResponse({"ok": False, "error": "The run is not waiting for a code."}, status=409)
    if request.POST.get("cancel") == "1":
        QuoteEngineJob.objects.filter(id=job.id).update(otp_cancelled=True)
        return JsonResponse({"ok": True})
    code = "".join(ch for ch in (request.POST.get("code") or "") if ch.isdigit())
    if not 4 <= len(code) <= 8:
        return JsonResponse({"ok": False, "error": "Enter the digits from the email."}, status=400)
    QuoteEngineJob.objects.filter(id=job.id).update(otp_code_enc=encrypt_secret(code))
    return JsonResponse({"ok": True})
