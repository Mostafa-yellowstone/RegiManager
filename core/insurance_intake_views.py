"""Public insurance intake portal and staff approval workflows."""

from __future__ import annotations

import hashlib
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .access import organizations_for_user
from .insurance_intake_approval import approve_insurance_intake
from .insurance_intake_constants import (
    COMMERCIAL_AUTO_INSURANCE_TYPES,
    PERSONAL_AUTO_INSURANCE_TYPES,
    insurance_intake_type_choices,
)
from .insurance_intake_forms import InsuranceIntakeEzlynxCaptureForm, InsuranceIntakeForm
from .insurance_permissions import can_manage_insurance_intake
from .models import InsuranceIntake, Organization
from .ratelimit import client_ip


def _check_insurance_intake_post_rate(request):
    import sys

    from django.conf import settings

    if settings.DEBUG or "test" in sys.argv:
        return True
    raw = f"insurance_intake_post:{client_ip(request)}"
    cache_key = "rl:" + hashlib.sha256(raw.encode()).hexdigest()[:32]
    count = cache.get(cache_key, 0)
    if count >= 5:
        return False
    cache.set(cache_key, count + 1, timeout=60)
    return True


def _render_native_insurance_intake(request, organization, token):
    if request.method == "POST":
        if not _check_insurance_intake_post_rate(request):
            messages.error(request, "Too many submissions. Please wait a minute and try again.")
            form = InsuranceIntakeForm(request.POST, request.FILES, organization=organization)
        else:
            form = InsuranceIntakeForm(request.POST, request.FILES, organization=organization)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        intake = form.save(commit=False)
                        intake.organization = organization
                        intake.additional_data = {
                            **(intake.additional_data or {}),
                            "portal_mode": "native",
                        }
                        intake.save()
                    return redirect(f"/insurance-intake/success/?portal_token={token}")
                except Exception:
                    messages.error(
                        request,
                        "An error occurred while saving your application. Please try again.",
                    )
    else:
        form = InsuranceIntakeForm(organization=organization)

    return render(
        request,
        "core/public_insurance_intake_form.html",
        {
            "form": form,
            "organization": organization,
            "portal_token": token,
            "insurance_type_choices": insurance_intake_type_choices(),
            "personal_auto_types_json": json.dumps(sorted(PERSONAL_AUTO_INSURANCE_TYPES)),
            "commercial_auto_types_json": json.dumps(sorted(COMMERCIAL_AUTO_INSURANCE_TYPES)),
        },
    )


def _render_ezlynx_capture_step(request, organization, token):
    if request.method == "POST":
        if not _check_insurance_intake_post_rate(request):
            messages.error(request, "Too many submissions. Please wait a minute and try again.")
            form = InsuranceIntakeEzlynxCaptureForm(request.POST)
        else:
            form = InsuranceIntakeEzlynxCaptureForm(request.POST)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        intake = form.save_intake(organization)
                    request.session[f"ezlynx_intake_{token}"] = intake.id
                    return redirect(f"/insurance-intake/{token}/?step=quote")
                except Exception:
                    messages.error(
                        request,
                        "An error occurred while saving your information. Please try again.",
                    )
    else:
        form = InsuranceIntakeEzlynxCaptureForm()

    return render(
        request,
        "core/public_insurance_intake_ezlynx_capture.html",
        {
            "form": form,
            "organization": organization,
            "portal_token": token,
            "ezlynx_quote_url": organization.insurance_ezlynx_quote_url,
        },
    )


def _render_ezlynx_quote_step(request, organization, token, ezlynx_url):
    intake = None
    intake_id = request.GET.get("intake_id") or request.session.get(f"ezlynx_intake_{token}")
    if intake_id:
        intake = InsuranceIntake.objects.filter(
            id=intake_id,
            organization=organization,
        ).first()

    return render(
        request,
        "core/public_insurance_intake_ezlynx_quote.html",
        {
            "organization": organization,
            "portal_token": token,
            "ezlynx_quote_url": ezlynx_url,
            "captured_intake": intake,
            "portal_mode": organization.insurance_intake_effective_portal_mode,
        },
    )


@ensure_csrf_cookie
def public_insurance_intake_portal(request, portal_token=None):
    token = portal_token or request.GET.get("portal_token")
    if not token:
        return render(request, "core/public_insurance_intake_start.html")

    organization = get_object_or_404(Organization, portal_token=token, is_active=True)
    if not organization.is_public_insurance_intake_enabled:
        return render(
            request,
            "core/public_insurance_intake_disabled.html",
            {"organization": organization},
        )

    portal_mode = organization.insurance_intake_effective_portal_mode
    ezlynx_url = (organization.insurance_ezlynx_quote_url or "").strip()

    if portal_mode == "native" or not ezlynx_url:
        if portal_mode != "native" and not ezlynx_url:
            messages.info(
                request,
                "Online quoting is not configured yet. Please use the form below or contact the agency.",
            )
        return _render_native_insurance_intake(request, organization, token)

    if portal_mode == "ezlynx_dual" and request.GET.get("step") != "quote":
        return _render_ezlynx_capture_step(request, organization, token)

    return _render_ezlynx_quote_step(request, organization, token, ezlynx_url)


def public_insurance_intake_success(request):
    token = request.GET.get("portal_token")
    organization = None
    if token:
        organization = Organization.objects.filter(portal_token=token).first()
    return render(
        request,
        "core/public_insurance_intake_success.html",
        {"organization": organization},
    )


def _redirect_insurance_space(org, tab="intake-queue"):
    from django.urls import reverse

    from .models import Space

    space = Space.objects.filter(organization=org, key="insurance").first()
    if space:
        url = reverse("inventory-detail", kwargs={"inventory_id": space.id})
        if tab:
            url += f"?tab={tab}"
        return redirect(url)
    return redirect("dashboard")


@login_required
@require_POST
def approve_insurance_intake_view(request, intake_id):
    organizations = organizations_for_user(request)
    with transaction.atomic():
        intake = get_object_or_404(
            InsuranceIntake.objects.select_for_update(),
            id=intake_id,
            organization__in=organizations,
        )
        if not can_manage_insurance_intake(
            request.user, intake.organization, is_owner=None
        ):
            messages.error(request, "You do not have permission to process insurance intakes.")
            return redirect("dashboard")

        if intake.status != InsuranceIntake.Status.PENDING:
            messages.error(request, "This intake has already been processed.")
            return _redirect_insurance_space(intake.organization)

        approve_insurance_intake(intake, request.user)
        messages.success(request, f"Insurance intake approved for {intake.name}.")
    return _redirect_insurance_space(intake.organization)


@login_required
@require_POST
def reject_insurance_intake_view(request, intake_id):
    organizations = organizations_for_user(request)
    with transaction.atomic():
        intake = get_object_or_404(
            InsuranceIntake.objects.select_for_update(),
            id=intake_id,
            organization__in=organizations,
        )
        if not can_manage_insurance_intake(
            request.user, intake.organization, is_owner=None
        ):
            messages.error(request, "You do not have permission to process insurance intakes.")
            return redirect("dashboard")

        if intake.status != InsuranceIntake.Status.PENDING:
            messages.error(request, "This intake has already been processed.")
            return _redirect_insurance_space(intake.organization)

        reason = (request.POST.get("rejection_reason") or "").strip()
        intake.status = InsuranceIntake.Status.REJECTED
        intake.processed_by = request.user
        intake.processed_at = timezone.now()
        if reason:
            intake.additional_data = {**(intake.additional_data or {}), "rejection_reason": reason}
        intake.save()
        messages.warning(request, f"Insurance intake rejected for {intake.name}.")
    return _redirect_insurance_space(intake.organization)
