"""Views for the Motor Club roadside assistance space."""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .http import deny_access
from .models import (
    Client,
    InsurancePolicy,
    MotorclubB2BPartner,
    MotorclubMembership,
    OrganizationMembership,
    Space,
)
from .motorclub_crm import (
    TIER_CHOICES,
    clients_with_insurance,
    enrich_membership,
    get_or_create_config,
    motorclub_dashboard_stats,
    split_profits_for_tier,
    tier_preview_rows,
)
from .space_access import require_space_access
from .views import _get_user_organizations


def _resolve_motorclub_access(request, space_id=None, card=None):
    organizations = _get_user_organizations(request)
    if card is None:
        card = get_object_or_404(
            Space,
            id=space_id,
            organization__in=organizations,
            key="motorclub",
        )

    if request.user.is_superuser:
        return card, True, None

    membership = OrganizationMembership.objects.filter(
        user=request.user,
        organization=card.organization,
        is_active=True,
        organization__is_active=True,
    ).first()
    if not membership:
        deny_access("Access denied.")

    is_owner = membership.role == OrganizationMembership.Role.OWNER
    require_space_access(membership, card)
    return card, is_owner, membership


def _motorclub_url(card, tab=None):
    from django.urls import reverse

    url = reverse("inventory-detail", kwargs={"inventory_id": card.id})
    if tab:
        url += f"?tab={tab}"
    return url


def _redirect_motorclub(card, tab=None):
    return redirect(_motorclub_url(card, tab))


def _parse_decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return default


def _parse_tier(value):
    try:
        tier = int(value)
    except (TypeError, ValueError):
        return None
    if tier in {35, 50, 75, 100}:
        return tier
    return None


def build_motorclub_space_context(request, card, is_owner, membership):
    active_org = card.organization
    config = get_or_create_config(active_org)
    stats = motorclub_dashboard_stats(card)

    search = request.GET.get("q", "").strip()
    channel_filter = request.GET.get("channel", "").strip()
    status_filter = request.GET.get("status", "").strip()
    tier_filter = request.GET.get("tier", "").strip()
    partner_filter = request.GET.get("b2b_partner", "").strip()

    memberships_qs = (
        MotorclubMembership.objects.filter(space=card)
        .select_related("client", "b2b_partner", "insurance_policy", "added_by")
        .order_by("-created_at")
    )
    if search:
        memberships_qs = memberships_qs.filter(
            Q(membership_number__icontains=search)
            | Q(client__first_name__icontains=search)
            | Q(client__last_name__icontains=search)
            | Q(b2b_partner__name__icontains=search)
        )
    if channel_filter:
        memberships_qs = memberships_qs.filter(channel=channel_filter)
    if status_filter:
        memberships_qs = memberships_qs.filter(status=status_filter)
    if tier_filter:
        parsed_tier = _parse_tier(tier_filter)
        if parsed_tier:
            memberships_qs = memberships_qs.filter(tier=parsed_tier)
    if partner_filter:
        memberships_qs = memberships_qs.filter(b2b_partner_id=partner_filter)

    page = Paginator(memberships_qs, 15).get_page(request.GET.get("page", 1))
    for row in page:
        enrich_membership(row)

    can_manage = is_owner or (membership and membership.can_deal_with_motorclub)

    return {
        "card": card,
        "active_org": active_org,
        "is_owner": is_owner,
        "can_manage_motorclub": can_manage,
        "stats": stats,
        "config": config,
        "tier_preview": tier_preview_rows(config),
        "tier_choices": TIER_CHOICES,
        "memberships_page": page,
        "memberships": page,
        "clients": Client.objects.filter(organization=active_org).order_by("first_name", "last_name")[:500],
        "insurance_clients": clients_with_insurance(active_org),
        "b2b_partners": MotorclubB2BPartner.objects.filter(
            organization=active_org,
            is_active=True,
        ).order_by("name"),
        "all_b2b_partners": MotorclubB2BPartner.objects.filter(organization=active_org).order_by("name"),
        "active_tab": request.GET.get("tab", "dashboard"),
        "search": search,
        "channel_filter": channel_filter,
        "status_filter": status_filter,
        "tier_filter": tier_filter,
        "partner_filter": partner_filter,
        "channel_choices": MotorclubMembership.ChannelChoices.choices,
        "status_choices": MotorclubMembership.StatusChoices.choices,
    }


@login_required
@require_POST
def save_motorclub_config(request, space_id):
    card, is_owner, membership = _resolve_motorclub_access(request, space_id=space_id)
    if not is_owner and not (membership and membership.can_deal_with_motorclub):
        deny_access("You do not have permission to update Motor Club configuration.")

    config = get_or_create_config(card.organization)
    config.tier_35_provider_take = _parse_decimal(request.POST.get("tier_35_provider_take"), config.tier_35_provider_take)
    config.tier_50_provider_take = _parse_decimal(request.POST.get("tier_50_provider_take"), config.tier_50_provider_take)
    config.tier_75_provider_take = _parse_decimal(request.POST.get("tier_75_provider_take"), config.tier_75_provider_take)
    config.tier_100_provider_take = _parse_decimal(request.POST.get("tier_100_provider_take"), config.tier_100_provider_take)
    config.provider_profit_notes = request.POST.get("provider_profit_notes", "").strip()
    config.psb_profit_notes = request.POST.get("psb_profit_notes", "").strip()
    config.save()
    messages.success(request, "Motor Club configuration saved.")
    return _redirect_motorclub(card, tab="configuration")


@login_required
@require_POST
def add_motorclub_membership(request, space_id):
    card, is_owner, membership = _resolve_motorclub_access(request, space_id=space_id)
    if not is_owner and not (membership and membership.can_deal_with_motorclub):
        deny_access("You do not have permission to add Motor Club memberships.")

    client_id = request.POST.get("client_id")
    client = get_object_or_404(Client, id=client_id, organization=card.organization)
    tier = _parse_tier(request.POST.get("tier"))
    if not tier:
        messages.error(request, "Select a valid plan tier ($35, $50, $75, or $100).")
        return _redirect_motorclub(card)

    channel = request.POST.get("channel", MotorclubMembership.ChannelChoices.DIRECT)
    if channel not in dict(MotorclubMembership.ChannelChoices.choices):
        channel = MotorclubMembership.ChannelChoices.DIRECT

    b2b_partner = None
    partner_id = request.POST.get("b2b_partner_id", "").strip()
    if partner_id:
        b2b_partner = MotorclubB2BPartner.objects.filter(
            id=partner_id,
            organization=card.organization,
        ).first()

    insurance_policy = None
    policy_id = request.POST.get("insurance_policy_id", "").strip()
    if policy_id:
        insurance_policy = InsurancePolicy.objects.filter(
            id=policy_id,
            organization=card.organization,
            client=client,
        ).first()

    config = get_or_create_config(card.organization)
    provider_profit = request.POST.get("provider_profit", "").strip()
    psb_profit = request.POST.get("psb_profit", "").strip()
    if provider_profit or psb_profit:
        provider_val = _parse_decimal(provider_profit)
        psb_val = _parse_decimal(psb_profit)
    else:
        provider_val, psb_val = split_profits_for_tier(tier, config)

    status = request.POST.get("status", MotorclubMembership.StatusChoices.ACTIVE)
    if status not in dict(MotorclubMembership.StatusChoices.choices):
        status = MotorclubMembership.StatusChoices.ACTIVE

    MotorclubMembership.objects.create(
        organization=card.organization,
        space=card,
        client=client,
        b2b_partner=b2b_partner,
        insurance_policy=insurance_policy,
        channel=channel,
        tier=tier,
        status=status,
        start_date=request.POST.get("start_date") or None,
        end_date=request.POST.get("end_date") or None,
        provider_profit=provider_val,
        psb_profit=psb_val,
        notes=request.POST.get("notes", "").strip(),
        added_by=request.user,
    )
    messages.success(request, f"Motor Club membership added for {client.name}.")
    return _redirect_motorclub(card, tab="members")


@login_required
@require_POST
def edit_motorclub_membership(request, membership_id):
    membership = get_object_or_404(
        MotorclubMembership.objects.select_related("space"),
        id=membership_id,
    )
    card, is_owner, m = _resolve_motorclub_access(request, card=membership.space)
    if not is_owner and not (m and m.can_deal_with_motorclub):
        deny_access("You do not have permission to edit Motor Club memberships.")

    tier = _parse_tier(request.POST.get("tier")) or membership.tier
    status = request.POST.get("status", membership.status)
    if status not in dict(MotorclubMembership.StatusChoices.choices):
        status = membership.status

    membership.tier = tier
    membership.status = status
    membership.channel = request.POST.get("channel", membership.channel)
    membership.start_date = request.POST.get("start_date") or None
    membership.end_date = request.POST.get("end_date") or None
    membership.notes = request.POST.get("notes", "").strip()
    membership.provider_profit = _parse_decimal(
        request.POST.get("provider_profit"),
        membership.provider_profit,
    )
    membership.psb_profit = _parse_decimal(
        request.POST.get("psb_profit"),
        membership.psb_profit,
    )

    partner_id = request.POST.get("b2b_partner_id", "").strip()
    membership.b2b_partner = (
        MotorclubB2BPartner.objects.filter(id=partner_id, organization=card.organization).first()
        if partner_id
        else None
    )
    membership.save()
    messages.success(request, "Motor Club membership updated.")
    return _redirect_motorclub(card, tab="members")


@login_required
@require_POST
def delete_motorclub_membership(request, membership_id):
    membership = get_object_or_404(
        MotorclubMembership.objects.select_related("space", "client"),
        id=membership_id,
    )
    card, is_owner, m = _resolve_motorclub_access(request, card=membership.space)
    if not is_owner:
        deny_access("Only PSB owners can delete Motor Club memberships.")

    client_name = membership.client.name
    membership.delete()
    messages.success(request, f"Removed Motor Club membership for {client_name}.")
    return _redirect_motorclub(card, tab="members")


@login_required
@require_POST
def add_motorclub_b2b_partner(request, space_id):
    card, is_owner, membership = _resolve_motorclub_access(request, space_id=space_id)
    if not is_owner and not (membership and membership.can_deal_with_motorclub):
        deny_access("You do not have permission to add B2B partners.")

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Partner company name is required.")
        return _redirect_motorclub(card, tab="b2b")

    MotorclubB2BPartner.objects.create(
        organization=card.organization,
        name=name,
        contact_name=request.POST.get("contact_name", "").strip(),
        phone=request.POST.get("phone", "").strip(),
        email=request.POST.get("email", "").strip(),
        notes=request.POST.get("notes", "").strip(),
    )
    messages.success(request, f"B2B partner '{name}' added.")
    return _redirect_motorclub(card, tab="b2b")


@login_required
@require_POST
def delete_motorclub_b2b_partner(request, partner_id):
    partner = get_object_or_404(MotorclubB2BPartner, id=partner_id)
    card = Space.objects.filter(organization=partner.organization, key="motorclub").first()
    if not card:
        deny_access("Motor Club space not found.")
    _, is_owner, membership = _resolve_motorclub_access(request, card=card)
    if not is_owner:
        deny_access("Only PSB owners can remove B2B partners.")

    name = partner.name
    partner.delete()
    messages.success(request, f"Removed B2B partner '{name}'.")
    return _redirect_motorclub(card, tab="b2b")
