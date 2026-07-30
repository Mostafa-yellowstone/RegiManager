"""Performance helpers for Insurance Space."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import calendar

from django.db.models import Count, Prefetch, Q, Sum

from .insurance_commissions import (
    build_adjusted_unearned_map,
    company_commission_summary,
    policy_unearned_commission,
    refund_total,
)
from .insurance_company_license import company_license_status
from .models import BankTransaction, InsuranceCompany, InsurancePolicy


def get_user_colors(username):
    h = sum(ord(c) for c in username) * 37 % 360
    return f"hsl({h}, 75%, 93%)", f"hsl({h}, 80%, 25%)"


def resolve_insurance_period_bounds(
    mode="monthly",
    month_offset=0,
    custom_from="",
    custom_to="",
    *,
    today=None,
):
    """Return inclusive start/end dates for the selected insurance CRM period."""
    today = today or date.today()
    if mode == "custom" and custom_from and custom_to:
        try:
            return (
                datetime.strptime(custom_from, "%Y-%m-%d").date(),
                datetime.strptime(custom_to, "%Y-%m-%d").date(),
            )
        except ValueError:
            pass

    yr, mo = today.year, today.month
    total_months = yr * 12 + (mo - 1) + month_offset
    yr = total_months // 12
    mo = (total_months % 12) + 1
    if mode == "quarterly":
        q_start_mo = ((mo - 1) // 3) * 3 + 1
        start = date(yr, q_start_mo, 1)
        end_mo = q_start_mo + 2
        end_yr = yr
        if end_mo > 12:
            end_mo -= 12
            end_yr += 1
        end = date(end_yr, end_mo, calendar.monthrange(end_yr, end_mo)[1])
    else:
        start = date(yr, mo, 1)
        end = date(yr, mo, calendar.monthrange(yr, mo)[1])
    return start, end


def previous_insurance_period_bounds(
    mode,
    month_offset,
    custom_from="",
    custom_to="",
    *,
    today=None,
):
    if mode == "quarterly":
        return resolve_insurance_period_bounds(
            mode, month_offset - 3, custom_from, custom_to, today=today
        )
    if mode == "custom" and custom_from and custom_to:
        try:
            start = datetime.strptime(custom_from, "%Y-%m-%d").date()
            end = datetime.strptime(custom_to, "%Y-%m-%d").date()
            duration = (end - start).days
            return start - timedelta(days=duration + 1), start - timedelta(days=1)
        except ValueError:
            return resolve_insurance_period_bounds(
                "monthly", month_offset - 1, today=today
            )
    return resolve_insurance_period_bounds(
        "monthly", month_offset - 1, custom_from, custom_to, today=today
    )


def filter_policies_by_quote_period(policy_qs, start, end):
    """Policies active in a period: bound on bound_date, open quotes on created date."""
    return policy_qs.filter(
        Q(bound_date__gte=start, bound_date__lte=end)
        | Q(
            bound_date__isnull=True,
            created_at__date__gte=start,
            created_at__date__lte=end,
        )
    )


def quote_period_ordering():
    return ["-bound_date", "-created_at"]


def period_stats(policy_qs, start, end):
    period_qs = filter_policies_by_quote_period(policy_qs, start, end)
    quotes = period_qs.filter(stage__in=InsurancePolicy.QUOTE_STAGES).count()
    bound = period_qs.filter(stage__in=InsurancePolicy.BOUND_STAGES).count()
    total = quotes + bound
    conversion = (bound / total * 100) if total > 0 else 0
    bound_stats = period_qs.filter(stage__in=InsurancePolicy.BOUND_STAGES, status="active").aggregate(
        premium=Sum("premium"),
        broker_fee=Sum("broker_fee"),
        earned_commission=Sum("commission_amount"),
    )
    return {
        "quotes": quotes,
        "bound": bound,
        "conversion": round(conversion, 1),
        "premium": float(bound_stats["premium"] or 0),
        "earned_commission": float(bound_stats["earned_commission"] or 0),
        "broker_fee": float(bound_stats["broker_fee"] or 0),
    }


def build_adjusted_unearned_for_org(insurance_companies, inactive_policies_qs):
    adjusted_unearned_map = {}
    inactive_by_company = {}
    for policy in inactive_policies_qs.iterator():
        inactive_by_company.setdefault(policy.insurance_company_id, []).append(policy)

    for company in insurance_companies:
        company_transactions = list(company.transactions.all())
        comp_inactive = inactive_by_company.get(company.id, [])
        comp_inactive.sort(key=lambda p: (p.inactive_date or p.start_date, p.id))
        company_refunded = refund_total(company_transactions)
        company_adjusted = build_adjusted_unearned_map(comp_inactive, company_refunded)
        adjusted_unearned_map.update(company_adjusted)
    return adjusted_unearned_map


def decorate_policies(policies, adjusted_unearned_map):
    for policy in policies:
        if policy.stage in InsurancePolicy.BOUND_STAGES and policy.status == "inactive":
            policy.unearned_commission = adjusted_unearned_map.get(
                policy.id, policy_unearned_commission(policy)
            )
        if policy.added_by:
            bg, text = get_user_colors(policy.added_by.username)
            policy.agent_bg_color = bg
            policy.agent_text_color = text


def build_company_summaries(insurance_companies, all_policies):
    summaries = []
    policies_by_company = {}
    for policy in all_policies.filter(stage__in=InsurancePolicy.BOUND_STAGES).iterator():
        policies_by_company.setdefault(policy.insurance_company_id, []).append(policy)

    for company in insurance_companies:
        comp_policies = policies_by_company.get(company.id, [])
        company_transactions = list(company.transactions.all())
        summary = company_commission_summary(comp_policies, company_transactions)
        comp_active_count = sum(
            1 for p in comp_policies if p.stage in InsurancePolicy.BOUND_STAGES and p.status == "active"
        )
        summaries.append({
            "id": company.id,
            "name": company.name,
            "active_count": comp_active_count,
            "earned_commission": summary["earned_commission"],
            "received_commission": summary["received_commission"],
            "unearned_commission": summary["unearned_commission"],
            "transaction_count": len(company_transactions),
            "license_status": company_license_status(company),
            "license_number": company.license_number or "",
            "broker_arrangement": company.broker_arrangement or "",
            "broker_arrangement_label": (
                company.get_broker_arrangement_display() if company.broker_arrangement else ""
            ),
        })
    return summaries


def build_agent_stats(policy_qs, insurance_memberships, start=None, end=None):
    scoped_policies = policy_qs
    if start is not None and end is not None:
        scoped_policies = filter_policies_by_quote_period(policy_qs, start, end)
    rows = {
        row["added_by_id"]: row
        for row in scoped_policies.filter(added_by__isnull=False)
        .values("added_by_id")
        .annotate(
            quotes_count=Count("id", filter=Q(stage__in=InsurancePolicy.QUOTE_STAGES)),
            policies_bound=Count("id", filter=Q(stage__in=InsurancePolicy.BOUND_STAGES)),
            total_premium=Sum("premium", filter=Q(stage__in=InsurancePolicy.BOUND_STAGES)),
            total_commission=Sum("commission_amount", filter=Q(stage__in=InsurancePolicy.BOUND_STAGES)),
            total_broker_fee=Sum("broker_fee", filter=Q(stage__in=InsurancePolicy.BOUND_STAGES)),
        )
    }

    agent_stats = []
    for membership in insurance_memberships:
        agent = membership.user
        stats = rows.get(agent.id, {})
        bg, text = get_user_colors(agent.username)
        agent_stats.append({
            "agent": agent,
            "user_id": agent.id,
            "fullname": agent.get_full_name() or agent.username,
            "quotes_count": stats.get("quotes_count", 0),
            "policies_bound": stats.get("policies_bound", 0),
            "total_premium": stats.get("total_premium") or Decimal("0"),
            "total_commission": stats.get("total_commission") or Decimal("0"),
            "total_broker_fee": stats.get("total_broker_fee") or Decimal("0"),
            "total_profit": (stats.get("total_commission") or Decimal("0"))
            + (stats.get("total_broker_fee") or Decimal("0")),
            "bg_color": bg,
            "text_color": text,
            "is_best": False,
            "is_second": False,
        })

    agent_stats.sort(key=lambda s: s["total_premium"], reverse=True)
    best_performer = None
    if agent_stats:
        agent_stats[0]["is_best"] = True
        best_performer = agent_stats[0]
    if len(agent_stats) > 1 and agent_stats[1]["total_premium"] > 0:
        agent_stats[1]["is_second"] = True
    return agent_stats, best_performer


def prefetch_insurance_companies(active_org):
    tx_qs = BankTransaction.objects.select_related("bank_account").order_by("-date", "-created_at")
    return InsuranceCompany.objects.filter(organization=active_org).prefetch_related(
        Prefetch("transactions", queryset=tx_qs)
    )
