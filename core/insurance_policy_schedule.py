"""Helpers for insurance policy payment schedule / next-due."""

from __future__ import annotations

from datetime import date

from django.utils import timezone

from .models import InsurancePolicy, InsurancePolicyInstallment


def next_payment_due(policy: InsurancePolicy, *, today: date | None = None):
    """
    Earliest unpaid installment due on/after today.
    If all unpaid rows are past-due, return the soonest unpaid due date.
    """
    today = today or timezone.localdate()
    unpaid = list(
        InsurancePolicyInstallment.objects.filter(policy=policy, is_paid=False)
        .order_by("due_date", "installment_number")
    )
    if not unpaid:
        return None
    upcoming = [row for row in unpaid if row.due_date >= today]
    if upcoming:
        return upcoming[0]
    return unpaid[0]


def summarize_insurance_schedule(policy: InsurancePolicy, *, today: date | None = None) -> dict:
    today = today or timezone.localdate()
    rows = list(
        InsurancePolicyInstallment.objects.filter(policy=policy).order_by(
            "due_date", "installment_number"
        )
    )
    unpaid = [r for r in rows if not r.is_paid]
    next_row = next_payment_due(policy, today=today)
    return {
        "installments": rows,
        "total": len(rows),
        "paid": len(rows) - len(unpaid),
        "open": len(unpaid),
        "next_due": next_row,
        "next_due_date": next_row.due_date if next_row else None,
        "next_due_amount": next_row.total_due if next_row else None,
    }
