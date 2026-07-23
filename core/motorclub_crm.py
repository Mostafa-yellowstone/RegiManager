"""Motor Club CRM helpers — tiers, profit splits, and dashboard stats."""

from decimal import Decimal

from django.db.models import Count, Q, Sum

from .models import (
    Client,
    InsurancePolicy,
    MotorclubB2BPartner,
    MotorclubConfig,
    MotorclubMembership,
)

MOTORCLUB_TIERS = (35, 50, 75, 100)

TIER_CHOICES = [
    (35, "$35"),
    (50, "$50"),
    (75, "$75"),
    (100, "$100"),
]


def get_or_create_config(organization):
    config, _ = MotorclubConfig.objects.get_or_create(organization=organization)
    return config


def provider_take_for_tier(tier, config):
    tier = int(tier)
    mapping = {
        35: config.tier_35_provider_take,
        50: config.tier_50_provider_take,
        75: config.tier_75_provider_take,
        100: config.tier_100_provider_take,
    }
    take = mapping.get(tier, Decimal("0.00"))
    return Decimal(str(take))


def split_profits_for_tier(tier, config):
    """Return (provider_profit, psb_profit) for a plan tier."""
    tier = int(tier)
    price = Decimal(str(tier))
    provider = provider_take_for_tier(tier, config)
    if provider > price:
        provider = price
    psb = price - provider
    return provider, psb


def tier_preview_rows(config):
    rows = []
    for tier in MOTORCLUB_TIERS:
        provider, psb = split_profits_for_tier(tier, config)
        rows.append(
            {
                "tier": tier,
                "price": Decimal(str(tier)),
                "provider_take": provider,
                "provider_profit": provider,
                "psb_profit": psb,
                "provider_field": f"tier_{tier}_provider_take",
            }
        )
    return rows


def get_client_motorclub_memberships(client):
    """
    Return Motor Club memberships that belong on this client's profile.

    Includes direct client links, insurance-policy links, and same-person
    matches within the PSB (SSN or driver license).
    """
    base_qs = MotorclubMembership.objects.filter(
        organization=client.organization,
    ).select_related("b2b_partner", "added_by", "insurance_policy", "client")

    filters = Q(client=client) | Q(insurance_policy__client=client)

    ssn = (client.ssn or "").strip()
    if ssn:
        filters |= Q(client__ssn=ssn)

    driver_license = (client.driver_license or "").strip()
    if driver_license:
        filters |= Q(client__driver_license=driver_license)

    return list(base_qs.filter(filters).order_by("-created_at").distinct())


def pick_active_motorclub(memberships):
    """Prefer an active plan; otherwise show the most recent membership."""
    if not memberships:
        return None
    return next(
        (m for m in memberships if m.status == MotorclubMembership.StatusChoices.ACTIVE),
        memberships[0],
    )


def enrich_membership(membership):
    membership.channel_label = membership.get_channel_display()
    membership.status_label = membership.get_status_display()
    membership.tier_label = membership.get_tier_display()
    if membership.added_by:
        membership.added_by_name = (
            membership.added_by.get_full_name().strip()
            or membership.added_by.username
        )
    else:
        membership.added_by_name = ""
    return membership


def motorclub_dashboard_stats(space):
    qs = MotorclubMembership.objects.filter(space=space)
    active_qs = qs.filter(status=MotorclubMembership.StatusChoices.ACTIVE)
    totals = active_qs.aggregate(
        provider_total=Sum("provider_profit"),
        psb_total=Sum("psb_profit"),
    )
    by_channel = {
        row["channel"]: row["count"]
        for row in qs.values("channel").annotate(count=Count("id"))
    }
    by_tier = {
        row["tier"]: row["count"]
        for row in active_qs.values("tier").annotate(count=Count("id"))
    }
    by_status = {
        row["status"]: row["count"]
        for row in qs.values("status").annotate(count=Count("id"))
    }
    return {
        "total_memberships": qs.count(),
        "active_memberships": active_qs.count(),
        "pending_memberships": by_status.get(MotorclubMembership.StatusChoices.PENDING, 0),
        "cancelled_memberships": by_status.get(MotorclubMembership.StatusChoices.CANCELLED, 0),
        "expired_memberships": by_status.get(MotorclubMembership.StatusChoices.EXPIRED, 0),
        "insurance_channel_count": by_channel.get("insurance_client", 0),
        "b2b_channel_count": by_channel.get("b2b", 0),
        "direct_channel_count": by_channel.get("direct", 0),
        "provider_revenue": totals["provider_total"] or Decimal("0"),
        "psb_revenue": totals["psb_total"] or Decimal("0"),
        "tier_35_count": by_tier.get(35, 0),
        "tier_50_count": by_tier.get(50, 0),
        "tier_75_count": by_tier.get(75, 0),
        "tier_100_count": by_tier.get(100, 0),
        "b2b_partner_count": MotorclubB2BPartner.objects.filter(
            organization=space.organization,
            is_active=True,
        ).count(),
    }


def _money_str(value) -> str:
    return f"{Decimal(value or 0):.2f}"


def serialize_motorclub_membership(membership) -> dict:
    """Companion-friendly membership row for owner APIs."""
    client_name = ""
    if membership.client_id:
        client_name = membership.client.name
    added_by = None
    if membership.added_by_id:
        added_by = (
            membership.added_by.get_full_name().strip()
            or membership.added_by.username
        )
    start = membership.start_date.isoformat() if membership.start_date else None
    end = membership.end_date.isoformat() if membership.end_date else None
    joined = start
    if not joined and membership.created_at:
        joined = membership.created_at.date().isoformat()
    partner_name = ""
    if membership.b2b_partner_id:
        partner_name = membership.b2b_partner.name
    return {
        "id": membership.id,
        "membership_number": membership.membership_number or f"MC-{membership.id}",
        "client_name": client_name,
        "status": membership.status,
        "channel": membership.channel,
        "channel_label": membership.get_channel_display(),
        "tier": membership.tier,
        "plan_type": f"${membership.tier}",
        "joined_date": joined,
        "start_date": start,
        "end_date": end,
        "provider_profit": _money_str(membership.provider_profit),
        "psb_profit": _money_str(membership.psb_profit),
        "added_by": added_by,
        "b2b_partner_name": partner_name or None,
    }


def build_motorclub_owner_summary(space) -> dict:
    """Snapshot KPIs for companion Motor Club space detail."""
    stats = motorclub_dashboard_stats(space)
    return {
        "total_memberships": stats["total_memberships"],
        "active_memberships": stats["active_memberships"],
        "pending_memberships": stats["pending_memberships"],
        "cancelled_memberships": stats["cancelled_memberships"],
        "expired_memberships": stats["expired_memberships"],
        "insurance_channel_count": stats["insurance_channel_count"],
        "b2b_channel_count": stats["b2b_channel_count"],
        "direct_channel_count": stats["direct_channel_count"],
        "provider_revenue": _money_str(stats["provider_revenue"]),
        "psb_revenue": _money_str(stats["psb_revenue"]),
        "tier_35_count": stats["tier_35_count"],
        "tier_50_count": stats["tier_50_count"],
        "tier_75_count": stats["tier_75_count"],
        "tier_100_count": stats["tier_100_count"],
        "b2b_partner_count": stats["b2b_partner_count"],
    }


def list_motorclub_memberships_for_org(
    organization,
    *,
    status: str | None = None,
    channel: str | None = None,
    limit: int = 50,
):
    qs = (
        MotorclubMembership.objects.filter(organization=organization)
        .select_related("client", "b2b_partner", "added_by")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    if channel:
        qs = qs.filter(channel=channel)
    return [serialize_motorclub_membership(m) for m in qs[:limit]]


def clients_with_insurance(organization):
    """Clients with bound insurance — ideal upsell targets for Motor Club."""
    policy_client_ids = (
        InsurancePolicy.objects.filter(
            organization=organization,
            stage="bound",
            status="active",
        )
        .values_list("client_id", flat=True)
        .distinct()
    )
    return Client.objects.filter(
        Q(id__in=policy_client_ids) | Q(source__iexact="insurance"),
        organization=organization,
    ).order_by("first_name", "last_name")[:500]


def insurance_policies_for_client(client):
    return InsurancePolicy.objects.filter(
        organization=client.organization,
        client=client,
        stage="bound",
    ).select_related("insurance_company").order_by("-created_at")
