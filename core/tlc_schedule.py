"""Installment schedule generation for TLC policies."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from .tlc_installments import build_installment_row
from .tlc_models import TLCInstallment, TLCPolicy, TLCPremiumBreakdown

ZERO = Decimal("0.00")


def normalize_policy_installment_numbers(policy: TLCPolicy) -> bool:
    """
    Persist numbering: deposit = 0, following bills = 1..N.
    Returns True when any row was renumbered.
    """
    rows = list(policy.installments.order_by("due_date", "installment_number", "id"))
    if not rows:
        return False

    deposits = [row for row in rows if row.is_deposit]
    bills = [row for row in rows if not row.is_deposit]
    target: dict[int, int] = {}

    if deposits:
        target[deposits[0].pk] = 0
        # Extra deposit-labelled rows keep unique numbers after the bill sequence.
        next_extra = len(bills) + 1
        for extra in deposits[1:]:
            target[extra.pk] = next_extra
            next_extra += 1

    for index, row in enumerate(bills, start=1):
        target[row.pk] = index

    if all(row.installment_number == target[row.pk] for row in rows):
        return False

    for index, row in enumerate(rows):
        TLCInstallment.objects.filter(pk=row.pk).update(installment_number=10000 + index)
    for pk, number in target.items():
        TLCInstallment.objects.filter(pk=pk).update(installment_number=number)
    return True


def _add_months(start: date, months: int) -> date:
    target = start + relativedelta(months=months)
    last_day = monthrange(target.year, target.month)[1]
    return target.replace(day=min(start.day, last_day))


def generate_installment_schedule(policy: TLCPolicy, *, replace_existing: bool = False) -> int:
    """
    Build installment rows from premium breakdown.
    Down payment / deposit is unnumbered (installment_number=0); monthly bills start at #1.
    """
    try:
        breakdown: TLCPremiumBreakdown = policy.premium_breakdown
    except TLCPremiumBreakdown.DoesNotExist:
        return 0

    per_fee = breakdown.installment_fee or ZERO
    start_date = policy.effective_date or date.today()
    created = 0

    if replace_existing:
        policy.installments.all().delete()

    down_payment = breakdown.down_payment or ZERO
    if down_payment > ZERO:
        row = build_installment_row(policy, down_payment, installment_fee=per_fee, apply_fee=False)
        TLCInstallment.objects.create(
            policy=policy,
            installment_number=0,
            due_date=start_date,
            amount=row["amount"],
            installment_fee=row["installment_fee"],
            commission_amount=row["commission_amount"],
            is_paid=False,
            balance=row["balance"],
            notes="Down Payment",
        )
        created += 1

    count = breakdown.number_of_installments or 0
    monthly = breakdown.monthly_installment or ZERO
    if count <= 0 or monthly <= ZERO:
        return created

    for offset in range(count):
        number = offset + 1
        due = _add_months(start_date, offset + (1 if down_payment > ZERO else 0))
        row = build_installment_row(policy, monthly, installment_fee=per_fee, apply_fee=True)
        TLCInstallment.objects.update_or_create(
            policy=policy,
            installment_number=number,
            defaults={
                "due_date": due,
                "amount": row["amount"],
                "installment_fee": row["installment_fee"],
                "commission_amount": row["commission_amount"],
                "is_paid": False,
                "balance": row["balance"],
                "notes": f"Bill #{offset + 1}",
            },
        )
        created += 1
    normalize_policy_installment_numbers(policy)
    from .tlc_installments import sync_installment_commissions

    sync_installment_commissions(policy)
    return created
