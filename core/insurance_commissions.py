"""Shared insurance commission calculations for CRM views."""

from decimal import Decimal, ROUND_HALF_UP

from .models import InsurancePolicy

UNEARNED_REFUND_CATEGORIES = frozenset({
    "Commission Refund",
    "Unearned Commission Refund",
})

COMMISSION_PAYMENT_CATEGORY = "Commission Payment"


def refund_total(transactions):
    """Sum of refund-category transactions that reduce unearned commission."""
    return sum(
        t.amount for t in transactions
        if t.category in UNEARNED_REFUND_CATEGORIES
    )


def received_commission_total(transactions):
    """Legacy helper: sum of Commission Payment income transactions."""
    return sum(
        t.amount for t in transactions
        if t.transaction_type == "income" and t.category == COMMISSION_PAYMENT_CATEGORY
    )


def received_commission_from_policies(policies):
    """Sum commission_amount for policies explicitly marked as received."""
    return sum(
        p.commission_amount for p in policies
        if getattr(p, "commission_received", False)
    )


def gross_earned_from_policies(policies):
    return sum(
        p.commission_amount for p in policies
        if p.stage in InsurancePolicy.BOUND_STAGES and p.status == "active"
    )


def outstanding_earned(gross_earned, received):
    return max(Decimal(str(gross_earned)) - Decimal(str(received)), Decimal("0.00"))


def _money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_unearned_commission(
    commission_amount,
    start_date,
    end_date,
    inactive_date,
    *,
    insurance_period_months=6,
):
    """
    Return commission that must be paid back after cancellation.

    Prorates by actual days from cancellation through expiration. Earned time
    (start through cancellation) reduces the payback; only the remaining
    policy term is unearned.
    """
    commission_amount = Decimal(str(commission_amount or "0"))
    if commission_amount <= 0 or not inactive_date:
        return Decimal("0.00")

    if start_date and end_date:
        if inactive_date >= end_date:
            return Decimal("0.00")
        if inactive_date <= start_date:
            return _money(commission_amount)

        policy_term_days = (end_date - start_date).days
        if policy_term_days <= 0:
            return _money(commission_amount)

        remaining_days = (end_date - inactive_date).days
        if remaining_days <= 0:
            return Decimal("0.00")

        return _money(commission_amount * Decimal(remaining_days) / Decimal(policy_term_days))

    total_months = Decimal(str(insurance_period_months or 6))
    if total_months <= 0:
        total_months = Decimal("6")
    return _money(commission_amount)


def policy_unearned_commission(policy):
    """Fresh unearned amount for display; does not rely on stored DB value."""
    if getattr(policy, "stage", None) not in InsurancePolicy.BOUND_STAGES or getattr(policy, "status", None) != "inactive":
        return Decimal("0.00")
    return calculate_unearned_commission(
        policy.commission_amount,
        policy.start_date,
        policy.end_date,
        policy.inactive_date,
        insurance_period_months=getattr(policy, "insurance_period_months", 6),
    )


def build_adjusted_unearned_map(inactive_policies, refund_amount):
    """FIFO distribution of refund amounts across inactive policies."""
    adjusted = {}
    remaining = Decimal(str(refund_amount))
    for p in inactive_policies:
        raw_val = policy_unearned_commission(p)
        if remaining >= raw_val:
            adjusted[p.id] = Decimal("0.00")
            remaining -= raw_val
        else:
            adjusted[p.id] = raw_val - remaining
            remaining = Decimal("0.00")
    return adjusted


def company_commission_summary(company_policies, company_transactions):
    """Return earned (outstanding), received, and unearned totals for a company."""
    gross = gross_earned_from_policies(company_policies)
    received = received_commission_from_policies(company_policies)
    earned = outstanding_earned(gross, received)

    inactive = [
        p for p in company_policies
        if p.stage in InsurancePolicy.BOUND_STAGES and p.status == "inactive"
    ]
    inactive.sort(key=lambda p: (p.inactive_date or p.start_date, p.id))
    refund_amt = refund_total(company_transactions)
    adjusted_map = build_adjusted_unearned_map(inactive, refund_amt)
    unearned = sum(
        adjusted_map.get(p.id, policy_unearned_commission(p))
        for p in inactive
    )

    return {
        "gross_earned": gross,
        "earned_commission": earned,
        "received_commission": received,
        "unearned_commission": unearned,
        "adjusted_unearned_map": adjusted_map,
    }
