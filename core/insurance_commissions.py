"""Shared insurance commission calculations for CRM views."""

from decimal import Decimal

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
    """Sum of Commission Payment income transactions."""
    return sum(
        t.amount for t in transactions
        if t.transaction_type == "income" and t.category == COMMISSION_PAYMENT_CATEGORY
    )


def gross_earned_from_policies(policies):
    return sum(
        p.commission_amount for p in policies
        if p.stage == "bound" and p.status == "active"
    )


def outstanding_earned(gross_earned, received):
    return max(Decimal(str(gross_earned)) - Decimal(str(received)), Decimal("0.00"))


def build_adjusted_unearned_map(inactive_policies, refund_amount):
    """FIFO distribution of refund amounts across inactive policies."""
    adjusted = {}
    remaining = Decimal(str(refund_amount))
    for p in inactive_policies:
        raw_val = p.unearned_commission
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
    received = received_commission_total(company_transactions)
    earned = outstanding_earned(gross, received)

    inactive = [
        p for p in company_policies
        if p.stage == "bound" and p.status == "inactive"
    ]
    inactive.sort(key=lambda p: (p.inactive_date or p.start_date, p.id))
    refund_amt = refund_total(company_transactions)
    adjusted_map = build_adjusted_unearned_map(inactive, refund_amt)
    unearned = sum(
        adjusted_map.get(p.id, p.unearned_commission)
        for p in inactive
    )

    return {
        "gross_earned": gross,
        "earned_commission": earned,
        "received_commission": received,
        "unearned_commission": unearned,
        "adjusted_unearned_map": adjusted_map,
    }
