"""Metric builders for the owner companion API."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .dashboard_metrics import daily_record_q, monthly_record_q, yearly_record_q
from .finance_hub_metrics import build_daily_payment_cards, build_month_goal_forecast
from .insurance_space_metrics import (
    period_stats,
    previous_insurance_period_bounds,
    resolve_insurance_period_bounds,
)
from .inventory_crm import inventory_dashboard_stats
from .models import (
    ClientIntake,
    InsuranceIntake,
    InsurancePolicy,
    Organization,
    OrganizationMembership,
    ServiceRecord,
    Space,
)
from .motorclub_crm import motorclub_dashboard_stats
from .space_access import filter_accessible_spaces


def _money(value) -> str:
    amount = value or Decimal("0")
    return str(amount.quantize(Decimal("0.01")))


def _period_bounds(period: str, *, today: date | None = None) -> tuple[date, date]:
    today = today or timezone.localdate()
    if period == "day":
        return today, today
    if period == "year":
        return today.replace(month=1, day=1), today
    return today.replace(day=1), today


def ensure_default_spaces(organization: Organization) -> None:
    defaults = [
        ("insurance", "Insurance", "Insurance CRM and Financial space"),
        ("knowledge_hub", "Knowledge Hub", "Training documents and educational material"),
        ("custom_inventory", "Custom Inventory", "Product inventory and sales"),
        ("motorclub", "Motor Club", "Motor club memberships and partners"),
        ("documents", "Documents", "Document management space"),
    ]
    for key, label, description in defaults:
        Space.objects.get_or_create(
            organization=organization,
            key=key,
            defaults={"label": label, "description": description},
        )


def spaces_for_membership(membership: OrganizationMembership, organization: Organization):
    ensure_default_spaces(organization)
    if membership.role == OrganizationMembership.Role.OWNER:
        return Space.objects.filter(organization=organization).order_by("label")
    return filter_accessible_spaces(membership, organization).order_by("label")


def build_dmv_finance_report(records, today: date) -> dict:
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    daily_qs = records.filter(daily_record_q(today))
    monthly_qs = records.filter(monthly_record_q(month_start, today))
    yearly_qs = records.filter(yearly_record_q(year_start, today))

    def _aggregate(qs):
        data = qs.aggregate(
            total_records=Count("id"),
            total_revenue=Sum("service_fee"),
            processing_fee=Sum("processing_fee"),
            referral_commission=Sum("referral_commission"),
            dmv_fee=Sum("dmv_fee"),
            sales_tax=Sum("sales_tax"),
            credit_card_fee=Sum("credit_card_fee"),
        )
        processing = data["processing_fee"] or Decimal("0")
        referral = data["referral_commission"] or Decimal("0")
        return {
            "total_records": data["total_records"] or 0,
            "total_revenue": _money(data["total_revenue"]),
            "gross_profit": _money(processing),
            "net_profit_after_referral": _money(processing - referral),
            "referral_commission": _money(referral),
            "dmv_fee": _money(data["dmv_fee"]),
            "sales_tax": _money(data["sales_tax"]),
            "credit_card_fee": _money(data["credit_card_fee"]),
            "completed": qs.filter(status="completed").count(),
            "pending": qs.filter(status="pending").count(),
            "failed": qs.filter(status="failed").count(),
            "refund": qs.filter(status="refund").count(),
        }

    return {
        "today": _aggregate(daily_qs),
        "month": _aggregate(monthly_qs),
        "year": _aggregate(yearly_qs),
        "as_of": today.isoformat(),
    }


def build_insurance_profit_report(organization_id: int, today: date) -> dict:
    month_start, month_end = resolve_insurance_period_bounds("monthly", today=today)
    year_start = today.replace(month=1, day=1)
    day_start, day_end = today, today
    prev_start, prev_end = previous_insurance_period_bounds("monthly", 0, today=today)

    policies = InsurancePolicy.objects.filter(organization_id=organization_id)

    def _bound_profit(start, end):
        bound_qs = policies.filter(
            stage__in=InsurancePolicy.BOUND_STAGES,
            bound_date__gte=start,
            bound_date__lte=end,
        )
        agg = bound_qs.aggregate(
            count=Count("id"),
            premium=Sum("premium"),
            commission=Sum("commission_amount"),
            broker_fee=Sum("broker_fee"),
        )
        commission = agg["commission"] or Decimal("0")
        broker = agg["broker_fee"] or Decimal("0")
        return {
            "bound_count": agg["count"] or 0,
            "premium": _money(agg["premium"]),
            "commission": _money(commission),
            "broker_fee": _money(broker),
            "total_profit": _money(commission + broker),
        }

    current_stats = period_stats(policies, month_start, month_end)
    previous_stats = period_stats(policies, prev_start, prev_end)

    return {
        "today": _bound_profit(day_start, day_end),
        "month": _bound_profit(month_start, month_end),
        "year": _bound_profit(year_start, today),
        "pipeline": {
            "quotes": current_stats["quotes"],
            "bound": current_stats["bound"],
            "conversion_pct": current_stats["conversion"],
            "previous_month": {
                "quotes": previous_stats["quotes"],
                "bound": previous_stats["bound"],
                "conversion_pct": previous_stats["conversion"],
            },
        },
        "as_of": today.isoformat(),
    }


def build_space_period_profit(space: Space, today: date) -> dict:
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    org_id = space.organization_id

    if space.key == "insurance":
        policies = InsurancePolicy.objects.filter(organization_id=org_id)

        def _profit(start, end):
            agg = policies.filter(
                stage__in=InsurancePolicy.BOUND_STAGES,
                bound_date__gte=start,
                bound_date__lte=end,
            ).aggregate(
                commission=Sum("commission_amount"),
                broker_fee=Sum("broker_fee"),
                count=Count("id"),
            )
            total = (agg["commission"] or Decimal("0")) + (agg["broker_fee"] or Decimal("0"))
            return {"profit": _money(total), "transactions": agg["count"] or 0}

        return {
            "key": space.key,
            "label": space.label,
            "today": _profit(today, today),
            "month": _profit(month_start, today),
            "year": _profit(year_start, today),
        }

    if space.key == "motorclub":
        stats = motorclub_dashboard_stats(space)
        return {
            "key": space.key,
            "label": space.label,
            "today": {"profit": "0.00", "transactions": 0},
            "month": {
                "profit": _money(stats["psb_revenue"]),
                "transactions": stats["active_memberships"],
            },
            "year": {
                "profit": _money(stats["psb_revenue"]),
                "transactions": stats["total_memberships"],
            },
            "active_memberships": stats["active_memberships"],
        }

    if space.key == "custom_inventory":
        stats = inventory_dashboard_stats(space)
        return {
            "key": space.key,
            "label": space.label,
            "today": {
                "profit": _money(stats["sales_today_total"]),
                "transactions": stats["sales_today_count"],
            },
            "month": {
                "profit": _money(stats["sales_month_total"]),
                "transactions": stats["sales_month_count"],
            },
            "year": {
                "profit": _money(stats["sales_month_total"]),
                "transactions": stats["invoice_count"],
            },
            "inventory_value": _money(stats["total_inventory_value"]),
        }

    if space.key == "documents":
        from .models import SpaceDocumentRecord

        qs = SpaceDocumentRecord.objects.filter(space=space)
        return {
            "key": space.key,
            "label": space.label,
            "today": {"profit": "0.00", "transactions": qs.filter(created_at__date=today).count()},
            "month": {"profit": "0.00", "transactions": qs.filter(created_at__date__gte=month_start).count()},
            "year": {"profit": "0.00", "transactions": qs.filter(created_at__date__gte=year_start).count()},
            "total_records": qs.count(),
        }

    return {
        "key": space.key,
        "label": space.label,
        "today": {"profit": "0.00", "transactions": 0},
        "month": {"profit": "0.00", "transactions": 0},
        "year": {"profit": "0.00", "transactions": 0},
    }


def build_system_profit_summary(
    organization: Organization,
    membership: OrganizationMembership,
    records,
    today: date,
) -> dict:
    dmv = build_dmv_finance_report(records, today)
    insurance = build_insurance_profit_report(organization.id, today)
    spaces = []
    total_today = Decimal("0")
    total_month = Decimal("0")
    total_year = Decimal("0")

    for space in spaces_for_membership(membership, organization):
        space_data = build_space_period_profit(space, today)
        spaces.append(space_data)
        for period_key, total_key in (
            ("today", "total_today"),
            ("month", "total_month"),
            ("year", "total_year"),
        ):
            profit = Decimal(space_data[period_key]["profit"])
            if period_key == "today":
                total_today += profit
            elif period_key == "month":
                total_month += profit
            else:
                total_year += profit

    total_today += Decimal(dmv["today"]["gross_profit"])
    total_month += Decimal(dmv["month"]["gross_profit"])
    total_year += Decimal(dmv["year"]["gross_profit"])
    total_today += Decimal(insurance["today"]["total_profit"])
    total_month += Decimal(insurance["month"]["total_profit"])
    total_year += Decimal(insurance["year"]["total_profit"])

    return {
        "dmv_core": dmv,
        "insurance": insurance,
        "spaces": spaces,
        "combined_profit": {
            "today": _money(total_today),
            "month": _money(total_month),
            "year": _money(total_year),
        },
    }


def build_month_comparison(records, compare_a: str, compare_b: str, *, mode: str = "month") -> dict | None:
    from django.utils import timezone as tz

    def _parse_month(value):
        try:
            month_start = tz.datetime.strptime(value, "%Y-%m").date().replace(day=1)
            if month_start.month == 12:
                next_month = month_start.replace(year=month_start.year + 1, month=1, day=1)
            else:
                next_month = month_start.replace(month=month_start.month + 1, day=1)
            return month_start, next_month
        except (ValueError, TypeError):
            return None, None

    def _add_months(d, months):
        y = d.year + (d.month - 1 + months) // 12
        m = (d.month - 1 + months) % 12 + 1
        return d.replace(year=y, month=m, day=1)

    a_start, a_end = _parse_month(compare_a)
    b_start, b_end = _parse_month(compare_b)
    if not a_start or not b_start:
        return None

    if mode == "quarter":
        a_end = _add_months(a_start, 3)
        b_end = _add_months(b_start, 3)

    def _stats(start, end):
        qs = records.filter(transaction_date__gte=start, transaction_date__lt=end)
        agg = qs.aggregate(
            revenue=Sum("service_fee"),
            records=Count("id"),
            gross_profit=Sum("processing_fee"),
            referral=Sum("referral_commission"),
        )
        gross = agg["gross_profit"] or Decimal("0")
        referral = agg["referral"] or Decimal("0")
        return {
            "revenue": _money(agg["revenue"]),
            "records": agg["records"] or 0,
            "gross_profit": _money(gross),
            "net_profit_after_referral": _money(gross - referral),
        }

    a_stats = _stats(a_start, a_end)
    b_stats = _stats(b_start, b_end)

    def _pct_delta(current, previous):
        cur = Decimal(current)
        prev = Decimal(previous)
        if prev == 0:
            return "0.0"
        return str(((cur - prev) / prev * Decimal("100")).quantize(Decimal("0.1")))

    return {
        "mode": mode,
        "period_a": {"label": a_start.strftime("%B %Y"), "stats": a_stats},
        "period_b": {"label": b_start.strftime("%B %Y"), "stats": b_stats},
        "deltas": {
            "revenue_pct": _pct_delta(b_stats["revenue"], a_stats["revenue"]),
            "records_pct": _pct_delta(b_stats["records"], a_stats["records"]),
            "gross_profit_pct": _pct_delta(b_stats["gross_profit"], a_stats["gross_profit"]),
            "net_profit_pct": _pct_delta(
                b_stats["net_profit_after_referral"],
                a_stats["net_profit_after_referral"],
            ),
        },
    }


def build_revenue_chart(records, today: date, months: int = 12) -> dict:
    month_start = today.replace(day=1)
    chart_end = month_start
    chart_start = (chart_end - timedelta(days=365)).replace(day=1)
    if months != 12:
        chart_start = month_start
        for _ in range(months - 1):
            if chart_start.month == 1:
                chart_start = chart_start.replace(year=chart_start.year - 1, month=12)
            else:
                chart_start = chart_start.replace(month=chart_start.month - 1)

    from django.db.models.functions import TruncMonth

    monthly_rows = (
        records.filter(transaction_date__gte=chart_start)
        .annotate(month=TruncMonth("transaction_date"))
        .values("month")
        .annotate(
            revenue=Sum("service_fee"),
            gross_profit=Sum("processing_fee"),
        )
        .order_by("month")
    )

    def _key(value):
        if hasattr(value, "date"):
            value = value.date()
        return value.strftime("%Y-%m")

    month_map = {
        _key(row["month"]): {
            "revenue": _money(row["revenue"]),
            "gross_profit": _money(row["gross_profit"]),
        }
        for row in monthly_rows
    }

    labels = []
    series_revenue = []
    series_profit = []
    cursor = chart_start
    while cursor <= chart_end:
        key = cursor.strftime("%Y-%m")
        labels.append(cursor.strftime("%b %Y"))
        point = month_map.get(key, {"revenue": "0.00", "gross_profit": "0.00"})
        series_revenue.append(point["revenue"])
        series_profit.append(point["gross_profit"])
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)

    return {"labels": labels, "revenue": series_revenue, "gross_profit": series_profit}


def build_process_summary(organization: Organization, today: date) -> dict:
    records = ServiceRecord.objects.filter(organization=organization)
    status_rows = records.values("status").annotate(count=Count("id"))
    status_map = dict(ServiceRecord.STATUS_CHOICES)
    status_totals = [
        {"status": row["status"], "label": status_map.get(row["status"], row["status"]), "count": row["count"]}
        for row in status_rows
    ]

    intake_summary = {}
    if organization.is_public_intake_enabled:
        intake_qs = ClientIntake.objects.filter(organization=organization)
        intake_summary = {
            "pending": intake_qs.filter(status=ClientIntake.Status.PENDING).count(),
            "processing": intake_qs.filter(status=ClientIntake.Status.PROCESSING).count(),
            "approved": intake_qs.filter(status=ClientIntake.Status.APPROVED).count(),
            "rejected": intake_qs.filter(status=ClientIntake.Status.REJECTED).count(),
        }

    insurance_intake_summary = {}
    if organization.is_public_insurance_intake_enabled:
        ins_qs = InsuranceIntake.objects.filter(organization=organization)
        insurance_intake_summary = {
            "pending": ins_qs.filter(status=InsuranceIntake.Status.PENDING).count(),
            "approved": ins_qs.filter(status=InsuranceIntake.Status.APPROVED).count(),
            "rejected": ins_qs.filter(status=InsuranceIntake.Status.REJECTED).count(),
        }

    policy_qs = InsurancePolicy.objects.filter(organization=organization)
    insurance_pipeline = {
        "quotes_open": policy_qs.filter(stage__in=InsurancePolicy.QUOTE_STAGES).count(),
        "bound_active": policy_qs.filter(
            stage__in=InsurancePolicy.BOUND_STAGES,
            status="active",
        ).count(),
        "bound_inactive": policy_qs.filter(
            stage__in=InsurancePolicy.BOUND_STAGES,
            status="inactive",
        ).count(),
    }

    return {
        "service_status": status_totals,
        "dmv_intake": intake_summary,
        "insurance_intake": insurance_intake_summary,
        "insurance_pipeline": insurance_pipeline,
        "as_of": today.isoformat(),
    }


def build_location_comparison(organizations, today: date) -> list[dict]:
    month_start = today.replace(day=1)
    org_stats_map = {
        row["organization_id"]: row
        for row in ServiceRecord.objects.filter(organization__in=organizations)
        .values("organization_id")
        .annotate(
            daily_profit=Sum("processing_fee", filter=daily_record_q(today)),
            monthly_profit=Sum("processing_fee", filter=monthly_record_q(month_start, today)),
            yearly_profit=Sum("processing_fee", filter=yearly_record_q(today.replace(month=1, day=1), today)),
            total_records=Count("id"),
        )
    }
    rows = []
    for org in organizations:
        stats = org_stats_map.get(org.id, {})
        rows.append(
            {
                "id": org.id,
                "name": org.name,
                "city": org.city,
                "state": org.state,
                "daily_profit": _money(stats.get("daily_profit")),
                "monthly_profit": _money(stats.get("monthly_profit")),
                "yearly_profit": _money(stats.get("yearly_profit")),
                "total_records": stats.get("total_records") or 0,
            }
        )
    rows.sort(key=lambda item: Decimal(item["monthly_profit"]), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows
