"""Pulse agent leaderboard: insurance binds and DMV desk work per team member for a date range."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum

from .models import InsurancePolicy, OrganizationMembership, ServiceRecord

ZERO = Decimal("0")


def _money(value) -> str:
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def build_agent_leaderboard(organization, start: date, end: date) -> dict:
    """
    Policies are credited to the agent who added them and counted by quote period (bound date,
    else created), like the CRM. DMV jobs are credited to the agent who handled them; refunds
    are left out. "Office keeps" is the processing fee minus any referral share.
    """
    from .insurance_space_metrics import filter_policies_by_quote_period

    policies = filter_policies_by_quote_period(
        InsurancePolicy.objects.filter(organization=organization), start, end
    ).filter(stage__in=InsurancePolicy.BOUND_STAGES)
    insurance_by_user = {
        row["added_by"]: row
        for row in policies.values("added_by").annotate(
            bound=Count("id"),
            premium=Sum("premium"),
            commission=Sum("commission_amount"),
            broker_fee=Sum("broker_fee"),
        )
    }

    dmv_jobs = (
        ServiceRecord.objects.filter(
            organization=organization,
            transaction_date__gte=start,
            transaction_date__lte=end,
            refunded_from__isnull=True,
        )
        .exclude(status="refund")
    )
    dmv_by_user = {
        row["handled_by"]: row
        for row in dmv_jobs.values("handled_by").annotate(
            jobs=Count("id"),
            processing=Sum("processing_fee"),
            referral=Sum("referral_commission"),
        )
    }

    memberships = (
        OrganizationMembership.objects.filter(organization=organization, is_active=True)
        .select_related("user")
        .order_by("user__first_name", "user__username")
    )
    def build_row(ins: dict, dmv: dict, **identity) -> dict:
        commission = ins.get("commission") or ZERO
        broker_fee = ins.get("broker_fee") or ZERO
        processing = dmv.get("processing") or ZERO
        office_keeps = max(processing - (dmv.get("referral") or ZERO), ZERO)
        return {
            **identity,
            "policies_bound": ins.get("bound") or 0,
            "premium": _money(ins.get("premium")),
            "commission": _money(commission),
            "broker_fee": _money(broker_fee),
            "dmv_jobs": dmv.get("jobs") or 0,
            "dmv_processing_fee": _money(processing),
            "dmv_office_keeps": _money(office_keeps),
            "total_earned": _money(commission + broker_fee + office_keeps),
        }

    rows = []
    member_ids = set()
    for membership in memberships:
        user = membership.user
        member_ids.add(user.id)
        rows.append(
            build_row(
                insurance_by_user.get(user.id, {}),
                dmv_by_user.get(user.id, {}),
                membership_id=membership.id,
                user_id=user.id,
                name=user.get_full_name() or user.username,
                role=membership.role,
            )
        )

    # Work by former staff or with no agent set still belongs in the totals.
    other_ins: dict = {}
    for user_id, row in insurance_by_user.items():
        if user_id in member_ids:
            continue
        for key in ("bound", "premium", "commission", "broker_fee"):
            other_ins[key] = (other_ins.get(key) or 0) + (row.get(key) or 0)
    other_dmv: dict = {}
    for user_id, row in dmv_by_user.items():
        if user_id in member_ids:
            continue
        for key in ("jobs", "processing", "referral"):
            other_dmv[key] = (other_dmv.get(key) or 0) + (row.get(key) or 0)
    if other_ins or other_dmv:
        rows.append(
            build_row(
                other_ins,
                other_dmv,
                membership_id=None,
                user_id=None,
                name="Others (former staff or unassigned)",
                role="",
            )
        )

    rows.sort(
        key=lambda row: (
            -Decimal(row["total_earned"]),
            -(row["policies_bound"] + row["dmv_jobs"]),
            row["name"].lower(),
        )
    )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    def total(key):
        return _money(sum((Decimal(row[key]) for row in rows), ZERO))

    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "agents": rows,
        "totals": {
            "policies_bound": sum(row["policies_bound"] for row in rows),
            "premium": total("premium"),
            "commission": total("commission"),
            "broker_fee": total("broker_fee"),
            "dmv_jobs": sum(row["dmv_jobs"] for row in rows),
            "dmv_office_keeps": total("dmv_office_keeps"),
            "total_earned": total("total_earned"),
        },
    }
