"""Performance helpers for Insurance Space."""

from decimal import Decimal

from django.db.models import Count, Prefetch, Q, Sum

from .insurance_commissions import (
    build_adjusted_unearned_map,
    company_commission_summary,
    refund_total,
)
from .models import BankTransaction, InsuranceCompany


def get_user_colors(username):
    h = sum(ord(c) for c in username) * 37 % 360
    return f"hsl({h}, 75%, 93%)", f"hsl({h}, 80%, 25%)"


def period_stats(policy_qs, start, end):
    period_qs = policy_qs.filter(created_at__date__gte=start, created_at__date__lte=end)
    quotes = period_qs.filter(stage="quote").count()
    bound = period_qs.filter(stage="bound").count()
    total = quotes + bound
    conversion = (bound / total * 100) if total > 0 else 0
    bound_stats = period_qs.filter(stage="bound", status="active").aggregate(
        premium=Sum("premium"),
        broker_fee=Sum("broker_fee"),
    )
    return {
        "quotes": quotes,
        "bound": bound,
        "conversion": round(conversion, 1),
        "premium": float(bound_stats["premium"] or 0),
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
        if policy.id in adjusted_unearned_map:
            policy.unearned_commission = adjusted_unearned_map[policy.id]
        if policy.added_by:
            bg, text = get_user_colors(policy.added_by.username)
            policy.agent_bg_color = bg
            policy.agent_text_color = text


def build_company_summaries(insurance_companies, all_policies):
    summaries = []
    policies_by_company = {}
    for policy in all_policies.filter(stage="bound").iterator():
        policies_by_company.setdefault(policy.insurance_company_id, []).append(policy)

    for company in insurance_companies:
        comp_policies = policies_by_company.get(company.id, [])
        company_transactions = list(company.transactions.all())
        summary = company_commission_summary(comp_policies, company_transactions)
        comp_active_count = sum(
            1 for p in comp_policies if p.stage == "bound" and p.status == "active"
        )
        summaries.append({
            "id": company.id,
            "name": company.name,
            "active_count": comp_active_count,
            "earned_commission": summary["earned_commission"],
            "received_commission": summary["received_commission"],
            "unearned_commission": summary["unearned_commission"],
            "transaction_count": len(company_transactions),
        })
    return summaries


def build_agent_stats(all_policies, insurance_memberships):
    rows = {
        row["added_by_id"]: row
        for row in all_policies.filter(added_by__isnull=False)
        .values("added_by_id")
        .annotate(
            quotes_count=Count("id", filter=Q(stage="quote")),
            policies_bound=Count("id", filter=Q(stage="bound")),
            total_premium=Sum("premium", filter=Q(stage="bound")),
            total_commission=Sum("commission_amount", filter=Q(stage="bound")),
            total_broker_fee=Sum("broker_fee", filter=Q(stage="bound")),
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
