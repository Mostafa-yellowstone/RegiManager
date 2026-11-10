"""Add, edit and remove wholesalers from the Insurance Companies page."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .http import deny_access
from .insurance_area_views import _insurance_access
from .insurance_wholesalers import WholesalerInputError, save_wholesaler
from .models import InsuranceWholesaler


def _finance_org(request):
    organization, _membership, _is_owner, can_view_banking = _insurance_access(request)
    if not can_view_banking:
        deny_access("You do not have permission to manage wholesalers.")
    return organization


@login_required
@require_POST
def save_insurance_wholesaler(request):
    organization = _finance_org(request)
    wholesaler = None
    raw_id = (request.POST.get("wholesaler_id") or "").strip()
    if raw_id:
        if not raw_id.isdigit():
            messages.error(request, "Choose a valid wholesaler.")
            return redirect("insurance-companies")
        wholesaler = get_object_or_404(InsuranceWholesaler, id=int(raw_id), organization=organization)
    try:
        saved = save_wholesaler(organization, request.POST, wholesaler)
    except WholesalerInputError as exc:
        messages.error(request, str(exc))
        return redirect("insurance-companies")
    messages.success(request, f"Wholesaler {saved.name} {'updated' if wholesaler else 'added'}.")
    return redirect("insurance-companies")


@login_required
@require_POST
def delete_insurance_wholesaler(request, wholesaler_id):
    organization = _finance_org(request)
    wholesaler = get_object_or_404(InsuranceWholesaler, id=wholesaler_id, organization=organization)
    name = wholesaler.name
    wholesaler.delete()
    messages.success(request, f"Wholesaler {name} removed. Its policies are now shown as written direct.")
    return redirect("insurance-companies")
