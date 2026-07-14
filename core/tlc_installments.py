"""Installment amount splitting: premium net of fee plus per-installment commission."""

from __future__ import annotations

from decimal import Decimal

ZERO = Decimal("0.00")


def split_installment_payment(
    gross_amount: Decimal,
    *,
    installment_fee: Decimal = ZERO,
    commission_rate: Decimal = ZERO,
    apply_fee: bool = True,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    Split a customer payment into premium portion, fee, commission, and total due.

    The fee is deducted from the gross amount (not added on top).
    Commission is calculated on the net premium portion.
  Returns: (net_premium, installment_fee, commission_amount, total_due)
    """
    gross = Decimal(gross_amount).quantize(Decimal("0.01"))
    fee = Decimal(installment_fee).quantize(Decimal("0.01")) if apply_fee and installment_fee else ZERO
    if fee > gross:
        fee = ZERO
    net_premium = (gross - fee).quantize(Decimal("0.01"))
    rate = Decimal(commission_rate or ZERO)
    commission = ZERO
    if rate and net_premium > ZERO:
        commission = (net_premium * rate / Decimal("100")).quantize(Decimal("0.01"))
    total_due = gross
    return net_premium, fee, commission, total_due


def policy_commission_rate(policy) -> Decimal:
    if policy.commission_rate:
        return Decimal(policy.commission_rate)
    if policy.carrier_commission_amount and hasattr(policy, "premium_breakdown"):
        try:
            breakdown = policy.premium_breakdown
        except Exception:
            breakdown = None
        if breakdown and breakdown.total_written_premium:
            premium = Decimal(breakdown.total_written_premium)
            if premium > ZERO:
                return (Decimal(policy.carrier_commission_amount) / premium * Decimal("100")).quantize(
                    Decimal("0.01")
                )
    return ZERO


def build_installment_row(
    policy,
    gross_amount: Decimal,
    *,
    installment_fee: Decimal = ZERO,
    apply_fee: bool = True,
) -> dict:
    """Return installment field defaults from a gross customer payment."""
    net, fee, commission, total = split_installment_payment(
        gross_amount,
        installment_fee=installment_fee,
        commission_rate=policy_commission_rate(policy),
        apply_fee=apply_fee,
    )
    return {
        "amount": net,
        "installment_fee": fee,
        "commission_amount": commission,
        "balance": total,
    }


def commission_on_premium(premium: Decimal, rate: Decimal) -> Decimal:
    """Agency commission = net premium × commission rate %."""
    premium = Decimal(premium or ZERO).quantize(Decimal("0.01"))
    rate = Decimal(rate or ZERO)
    if premium <= ZERO or rate <= ZERO:
        return ZERO
    return (premium * rate / Decimal("100")).quantize(Decimal("0.01"))


def annotate_installment_display_numbers(installments) -> list:
    """
    Deposit/down payment shows as —, then bills display as 1..N regardless of stored number.
    Fixes legacy schedules where deposit was #1 and bills were 2..10.
    """
    bill = 0
    for row in installments:
        if row.is_deposit:
            row.ui_number = "—"
        else:
            bill += 1
            row.ui_number = str(bill)
    return list(installments)


def sync_installment_commissions(policy, *, save: bool = True) -> int:
    """Recompute each installment's commission_amount from net premium × policy rate."""
    rate = policy_commission_rate(policy)
    updated = 0
    for row in policy.installments.all():
        commission = commission_on_premium(row.amount, rate)
        if Decimal(row.commission_amount or ZERO).quantize(Decimal("0.01")) != commission:
            row.commission_amount = commission
            if save:
                row.save(update_fields=["commission_amount"])
            updated += 1
    return updated
