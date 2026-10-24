"""Client profile actions for households and coverage gaps."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .access import has_active_org_access
from .http import deny_access
from .insurance_client_insights import (
    create_gap_lead,
    dismiss_gap,
    dismiss_suggestion,
    find_gap,
    household_for,
    link_household,
    unlink_household,
)
from .models import Client
from .products import can_use_insurance

SEARCH_LIMIT = 8


def _client_for(request, client_id) -> Client:
    client = get_object_or_404(Client.objects.select_related("organization"), id=client_id)
    if not has_active_org_access(request.user, client.organization_id):
        deny_access("Access denied.")
    if not can_use_insurance(request.user, client.organization):
        deny_access("You do not have access to Insurance.")
    return client


def _other_client(client, raw_id) -> Client | None:
    try:
        other_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    return Client.objects.filter(id=other_id, organization_id=client.organization_id).exclude(id=client.id).first()


def _back(client, anchor: str):
    return redirect(f"{reverse('client-detail', args=[client.id])}#{anchor}")


@login_required
@require_POST
def household_link(request, client_id):
    client = _client_for(request, client_id)
    other = _other_client(client, request.POST.get("other_id"))
    if other is None:
        messages.error(request, "Pick a client from this office.")
        return _back(client, "household")
    household = link_household(client, other, relationship=request.POST.get("relationship", ""), user=request.user)
    messages.success(request, f"{other.name} added to {household.name}.")
    return _back(client, "household")


@login_required
@require_POST
def household_unlink(request, client_id):
    client = _client_for(request, client_id)
    household = household_for(client)
    member = _other_client(client, request.POST.get("member_id")) if request.POST.get("member_id") else client
    if household is None or member is None or household_for(member) != household:
        messages.error(request, "That client is not in this household.")
        return _back(client, "household")
    unlink_household(member)
    messages.success(request, f"{member.name} removed from the household.")
    return _back(client, "household")


@login_required
@require_POST
def household_dismiss(request, client_id):
    client = _client_for(request, client_id)
    other = _other_client(client, request.POST.get("other_id"))
    if other is not None:
        dismiss_suggestion(client, other, request.user)
    return _back(client, "household")


@login_required
@require_GET
def household_search(request, client_id):
    client = _client_for(request, client_id)
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    query = (
        Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(business_name__icontains=q)
        | Q(phone_number__icontains=q)
    )
    parts = q.split()
    if len(parts) >= 2:
        query |= Q(first_name__icontains=parts[0], last_name__icontains=parts[-1])
    results = (
        Client.objects.filter(organization_id=client.organization_id)
        .filter(query)
        .exclude(id=client.id)
        .order_by("last_name", "first_name")[:SEARCH_LIMIT]
    )
    return JsonResponse(
        {
            "results": [
                {"id": c.id, "name": c.name, "detail": " · ".join(b for b in (c.phone_number, c.city) if b)}
                for c in results
            ]
        }
    )


@login_required
@require_POST
def gap_quote(request, client_id):
    client = _client_for(request, client_id)
    gap = find_gap(client, (request.POST.get("gap_key") or "").strip())
    if gap is None:
        messages.error(request, "That coverage gap is no longer open.")
        return _back(client, "coverage-gaps")
    lead = create_gap_lead(client, gap, request.user)
    if lead.assigned_to_id:
        agent = lead.assigned_to.user.get_full_name() or lead.assigned_to.user.username
        messages.success(request, f"Quote request for {gap.title} sent to {agent}.")
    else:
        messages.success(request, f"Quote request for {gap.title} is waiting in the unassigned queue.")
    return _back(client, "coverage-gaps")


@login_required
@require_POST
def gap_dismiss(request, client_id):
    client = _client_for(request, client_id)
    gap_key = (request.POST.get("gap_key") or "").strip()[:60]
    if gap_key:
        dismiss_gap(client, gap_key, request.user, (request.POST.get("note") or "").strip())
        messages.success(request, "Coverage gap dismissed.")
    return _back(client, "coverage-gaps")
