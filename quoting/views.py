"""Signed-in quoting desk. A browser request never attaches a portal session."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.http import deny_access
from core.insurance_quote_permissions import can_update_assigned_lead
from core.insurance_quote_pipeline_models import InsuranceQuoteLead
from core.products import active_membership, active_organization_for, can_use_insurance
from quoting.carriers.registry import REGISTRY
from quoting.demo.scenarios import scenario_form
from quoting.engine.secrets import status_for
from quoting.intake import ny_today
from quoting.models import QuoteAttempt, QuoteJob
from quoting.prefill import form_from_lead
from quoting.present import render_desk
from quoting.service import run_from_form

BANNER = (
    "Fixture premiums are illustrative and are not carrier rates. "
    "Portal readiness only checks that environment variables are set. "
    "This page does not log in, and it does not bypass MFA or a bot check."
)
PREFILL_NOTE = (
    " This lead was copied onto the form. Limits, license state, use, and driving history that were not on the lead were left blank."
)


def _plain_form(data) -> dict:
    if hasattr(data, "lists"):
        plain = {}
        for key, values in data.lists():
            if key in ("csrfmiddlewaretoken", "carriers_submitted"):
                continue
            plain[key] = values if len(values) > 1 else (values[0] if values else "")
        return plain
    return {
        key: value
        for key, value in data.items()
        if key not in ("csrfmiddlewaretoken", "carriers_submitted")
    }


def _applicant(data) -> str:
    if hasattr(data, "getlist"):
        first = (data.get("insured_first_name") or "").strip()
        last = (data.get("insured_last_name") or "").strip()
    else:
        first = str(data.get("insured_first_name") or "").strip()
        last = str(data.get("insured_last_name") or "").strip()
    return " ".join(part for part in (first, last) if part)


def _save_job(user, organization, data, result) -> QuoteJob:
    job = QuoteJob.objects.create(
        organization=organization,
        created_by=user,
        mode=result.mode,
        line="personal_auto",
        jurisdiction="NY",
        status=result.status,
        applicant_label=_applicant(data)[:200],
        intake=_plain_form(data),
        missing=[issue.to_dict() for issue in result.issues],
    )
    for item in result.results:
        offer = item.offer
        blocker = item.blocker
        QuoteAttempt.objects.create(
            job=job,
            carrier_key=item.carrier_key,
            carrier_name=item.carrier_name,
            status=item.status,
            blocker_code="" if blocker is None else blocker.code,
            detail="" if blocker is None else blocker.detail,
            missing=[] if blocker is None else list(blocker.missing),
            quote_number="" if offer is None else offer.quote_number,
            term_premium=None if offer is None else offer.term_premium,
            term_months=None if offer is None else offer.term_months,
            source="" if offer is None else offer.source,
        )
    return job


@login_required
@require_http_methods(["GET", "POST"])
def desk(request):
    organization = active_organization_for(request)
    membership = None if request.user.is_superuser else active_membership(request.user, organization)
    if not can_use_insurance(request.user, organization, membership):
        deny_access("You do not have access to Insurance.")

    lead_key = (request.POST.get("lead") if request.method == "POST" else request.GET.get("lead")) or ""
    lead = None
    if lead_key.isdigit():
        lead = (
            InsuranceQuoteLead.objects.filter(id=int(lead_key), organization=organization)
            .prefetch_related("additional_drivers", "additional_vehicles")
            .first()
        )
        if lead is None or not can_update_assigned_lead(request.user, lead, membership=membership):
            deny_access("You cannot quote this lead.")

    today = ny_today()
    scenario = None
    banner = BANNER
    saved_job_id = None
    if request.method == "POST":
        form = request.POST
        result = run_from_form(form, today=today)
        saved_job_id = _save_job(request.user, organization, form, result).id
    else:
        scenario = (request.GET.get("scenario") or "").strip()
        loaded = scenario_form(scenario, today) if scenario else None
        if loaded is not None:
            form = loaded
        elif lead is not None:
            form = form_from_lead(lead)
            scenario = None
            banner = BANNER + PREFILL_NOTE
        else:
            scenario = "clean"
            form = scenario_form(scenario, today)
        result = None

    back_url = reverse("insurance-pipeline")
    back_label = "Back to the quote pipeline"
    if lead is not None:
        back_url = reverse("insurance-quote-worksheet", args=[lead.id])
        back_label = "Back to this quote"

    html = render_desk(
        form=form,
        result=result,
        secrets=status_for(REGISTRY.for_line("personal_auto", "NY")),
        csrf_token=get_token(request),
        banner=banner,
        back_url=back_url,
        back_label=back_label,
        saved_job_id=saved_job_id,
        scenario=scenario,
        lead_id=str(lead.id) if lead is not None else None,
    )
    return HttpResponse(html)
