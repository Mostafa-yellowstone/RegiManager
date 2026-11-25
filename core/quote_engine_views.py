"""Quote engine page for one pipeline lead: fill the missing details, run, see results."""
from __future__ import annotations

import threading
from datetime import datetime
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .http import deny_access
from .carrier_credentials_models import CarrierCredential
from .insurance_quote_permissions import can_edit_quote_lead, can_manage_quote_distribution, membership_for_org
from .insurance_quote_pipeline_models import InsuranceQuoteLead
from .insurance_quote_pipeline_views import _active_org
from .quote_followup_models import STEP_KEYS, mark_step
from .insurance_quote_pipeline_models import BODILY_INJURY_LIMITS, DEFAULT_BODILY_INJURY
from .quote_engine.lead_bridge import (
    FLAT_FIELDS,
    default_effective_date,
    flat_to_extra,
    lead_to_request,
    run_for_lead,
    run_job,
)
from .quote_engine.validators import validate_quote_request


def start_job(job_id: int, extra: dict) -> None:
    """Runs in a background thread so the page can ask for the login code while the portal waits."""
    threading.Thread(target=run_job, args=(job_id, extra), daemon=True).start()


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
        update_fields = ["quote_details", "effective_date", "bodily_injury_limit", "updated_at"]
        if flat.get("gender") in ("male", "female", "other"):
            lead.gender = flat["gender"]
            update_fields.append("gender")
        lead.save(update_fields=update_fields)
        if request.POST.get("action") == "run":
            extra = flat_to_extra(flat)
            errors_now = [i for i in validate_quote_request(lead_to_request(lead, extra)) if i.severity == "error"]
            if errors_now:
                report = run_for_lead(lead, extra, user=request.user, save=True,
                                      spend_approved=request.POST.get("spend_approved") == "1")
                if report.blocked and request.headers.get("X-Requested-With") != "quote-engine":
                    messages.error(request, "Fix the items below, then run again. Nothing was sent to any carrier.")
            else:
                from .quote_engine_models import QuoteEngineJob

                cred = CarrierCredential.objects.filter(
                    organization=org, line="auto", enabled=True, carrier_key="progressive"
                ).exclude(password_enc="").first()
                job = QuoteEngineJob.objects.create(
                    lead=lead, created_by=request.user,
                    spend_approved=request.POST.get("spend_approved") == "1",
                    otp_carrier="Progressive" if cred else "",
                    otp_hint_email=(cred.otp_email if cred else ""),
                )
                start_job(job.id, extra)
                if request.headers.get("X-Requested-With") == "quote-engine":
                    return JsonResponse({
                        "job_id": job.id,
                        "status_url": reverse("quote-engine-job-status", args=[lead.id, job.id]),
                        "otp_url": reverse("quote-engine-job-otp", args=[lead.id, job.id]),
                    })
                return redirect(reverse("quote-engine-lead", args=[lead.id]) + f"?job={job.id}")
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
    if not flat.get("gender") and lead.gender:
        flat["gender"] = lead.gender
    if report is None:
        latest = lead.engine_runs.exclude(results=[]).first()
        if latest is not None:
            report = SimpleNamespace(blocked=False, results=latest.results)
    issues = report.issues if report and hasattr(report, "issues") else validate_quote_request(lead_to_request(lead, flat_to_extra(flat)))
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity != "error"]
    line = lead_to_request(lead, flat_to_extra(flat))["line_of_business"]
    progressive = (
        CarrierCredential.objects.filter(organization=org, carrier_key="progressive", line="auto").order_by("id").first()
    )
    can_manage = can_manage_quote_distribution(request.user, org, membership=membership_for_org(request.user, org))
    return render(request, "core/insurance_quote_engine.html", {
        "lead": lead, "flat": flat, "errors": errors, "warnings": warnings, "report": report,
        "is_commercial": line == "commercial_auto", "line": line,
        "ready": not errors, "past_runs": lead.engine_runs.all()[:5],
        "documents": lead.documents.all(),
        "bi_limits": BODILY_INJURY_LIMITS,
        "extra_vehicles": lead.additional_vehicles.all(),
        "insurance_space": True,
        "progressive_login": progressive,
        "progressive_login_url": reverse("insurance-progressive") if can_manage else "",
        "job_id": request.GET.get("job", ""),
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
    if job.status == "done" and job.run_id:
        out["results"] = [
            {"carrier": r["carrier"], "status": r["status"], "premium_term": r.get("premium_term"), "detail": r.get("detail", "")}
            for r in job.run.results
        ]
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
