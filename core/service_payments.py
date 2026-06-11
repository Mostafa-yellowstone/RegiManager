"""Payment ledger helpers for service receipts (transmittal / outstanding balances)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from .models import ServiceRecord, ServiceRecordPayment

PAYMENT_METHOD_KEYS = frozenset(dict(ServiceRecord.PAYMENT_METHODS).keys())


@dataclass
class LedgerDisplayRow:
    entry: object
    is_opening: bool
    payment_date: date
    description: str
    line_total: Decimal | None
    line_paid: Decimal
    balance_after: Decimal
    payment_method_label: str


def normalize_payment_method(value):
    method = (value or "cash").strip()
    return method if method in PAYMENT_METHOD_KEYS else "cash"


def payment_method_label(method):
    return dict(ServiceRecord.PAYMENT_METHODS).get(method, method or "Cash")


def parse_payment_date(value, default=None):
    """Parse YYYY-MM-DD from form input; fall back to default (usually today)."""
    default = default or timezone.localdate()
    raw = (value or "").strip()
    if not raw:
        return default
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return default


def _transaction_label(record):
    if record.transaction_type == "transmittal":
        return "Transmittal"
    return "Transaction"


def _total_due(record):
    return record.service_fee or Decimal("0")


def _needs_opening_row(record):
    total = _total_due(record)
    paid = record.paid_amount or Decimal("0")
    balance = total - paid
    if balance < Decimal("0"):
        balance = Decimal("0")
    return (
        record.transaction_type == "transmittal"
        or balance > Decimal("0")
        or paid < total
    )


def _initial_paid_at_creation(record):
    """Down payment captured on the transaction date — not follow-up balance payments."""
    initial = (
        record.payment_entries.filter(
            entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
            notes="Initial payment",
        )
        .order_by("payment_date", "created_at", "id")
        .first()
    )
    if initial:
        return initial.amount or Decimal("0")

    follow_up_total = Decimal("0")
    for entry in record.payment_entries.filter(
        entry_type=ServiceRecordPayment.ENTRY_PAYMENT
    ).exclude(notes="Initial payment"):
        follow_up_total += entry.amount or Decimal("0")

    paid = record.paid_amount or Decimal("0")
    initial_paid = paid - follow_up_total
    if initial_paid < Decimal("0"):
        initial_paid = Decimal("0")
    return initial_paid


def ensure_opening_ledger_entry(record, *, recorded_by=None):
    """
    Create or refresh the opening row (transaction date, total due, down payment,
    outstanding after down payment). Idempotent — safe to call before every receipt render.
    """
    if not _needs_opening_row(record):
        return None

    total = _total_due(record)
    initial_paid = _initial_paid_at_creation(record)
    balance = total - initial_paid
    if balance < Decimal("0"):
        balance = Decimal("0")
    payment_date = record.transaction_date or timezone.localdate()

    opening = record.payment_entries.filter(
        entry_type=ServiceRecordPayment.ENTRY_OPENING
    ).first()
    if opening:
        updates = {}
        if opening.line_total != total:
            updates["line_total"] = total
        if opening.payment_date != payment_date:
            updates["payment_date"] = payment_date
        has_follow_up = record.payment_entries.filter(
            entry_type=ServiceRecordPayment.ENTRY_PAYMENT
        ).exclude(notes="Initial payment").exists()
        if not has_follow_up and opening.line_paid != initial_paid:
            updates["line_paid"] = initial_paid
        if updates:
            ServiceRecordPayment.objects.filter(pk=opening.pk).update(**updates)
        return opening

    return ServiceRecordPayment.objects.create(
        service_record=record,
        entry_type=ServiceRecordPayment.ENTRY_OPENING,
        amount=Decimal("0"),
        line_total=total,
        line_paid=initial_paid,
        balance_after=balance,
        payment_method=normalize_payment_method(record.payment_method),
        payment_date=payment_date,
        cc_fee=Decimal("0"),
        notes=f"{_transaction_label(record)} transaction",
        recorded_by=recorded_by,
    )


def dedupe_ledger_entries(record):
    """
    Remove duplicate payment rows that repeat the opening down payment
    (common after backfill migration + opening row).
    """
    opening = record.payment_entries.filter(
        entry_type=ServiceRecordPayment.ENTRY_OPENING
    ).first()
    if not opening:
        return

    qs = record.payment_entries.filter(entry_type=ServiceRecordPayment.ENTRY_PAYMENT)
    qs.filter(notes="Initial payment").delete()

    opening_paid = opening.line_paid or Decimal("0")
    if opening_paid > Decimal("0"):
        qs.filter(
            amount=opening_paid,
            payment_date=opening.payment_date,
        ).delete()


def reconcile_ledger_balances(record):
    """Recalculate balance_after on every ledger line from running payments."""
    dedupe_ledger_entries(record)
    entries = list(
        record.payment_entries.order_by("payment_date", "created_at", "id")
    )
    total_due = _total_due(record)
    cumulative_paid = Decimal("0")

    for entry in entries:
        if entry.entry_type == ServiceRecordPayment.ENTRY_OPENING:
            cumulative_paid = entry.line_paid or Decimal("0")
            if cumulative_paid > total_due:
                cumulative_paid = total_due
            balance = total_due - cumulative_paid
            if balance < Decimal("0"):
                balance = Decimal("0")
            updates = {}
            if entry.line_total != total_due:
                updates["line_total"] = total_due
            if entry.balance_after != balance:
                updates["balance_after"] = balance
            if updates:
                ServiceRecordPayment.objects.filter(pk=entry.pk).update(**updates)
        else:
            amt = entry.amount or Decimal("0")
            cumulative_paid += amt
            if cumulative_paid > total_due:
                cumulative_paid = total_due
            balance = total_due - cumulative_paid
            if balance < Decimal("0"):
                balance = Decimal("0")
            if entry.balance_after != balance:
                ServiceRecordPayment.objects.filter(pk=entry.pk).update(
                    balance_after=balance
                )


def compute_ledger_rows(record) -> list[LedgerDisplayRow]:
    """Build display rows with correct running outstanding balance."""
    ensure_opening_ledger_entry(record)
    reconcile_ledger_balances(record)
    entries = list(
        record.payment_entries.order_by("payment_date", "created_at", "id")
    )
    if not entries:
        return []

    total_due = _total_due(record)
    cumulative_paid = Decimal("0")
    rows: list[LedgerDisplayRow] = []

    for entry in entries:
        method_label = entry.get_payment_method_display()
        if entry.entry_type == ServiceRecordPayment.ENTRY_OPENING:
            opening_paid = entry.line_paid or Decimal("0")
            cumulative_paid = min(opening_paid, total_due)
            balance = total_due - cumulative_paid
            txn = _transaction_label(record)
            rows.append(
                LedgerDisplayRow(
                    entry=entry,
                    is_opening=True,
                    payment_date=entry.payment_date,
                    description=f"{txn} transaction",
                    line_total=entry.line_total or total_due,
                    line_paid=opening_paid,
                    balance_after=balance,
                    payment_method_label=method_label,
                )
            )
        else:
            amt = entry.amount or Decimal("0")
            cumulative_paid = min(cumulative_paid + amt, total_due)
            balance = total_due - cumulative_paid
            desc = (entry.notes or "Payment").strip()
            if method_label.lower() not in desc.lower():
                desc = f"{method_label} — {desc}"
            rows.append(
                LedgerDisplayRow(
                    entry=entry,
                    is_opening=False,
                    payment_date=entry.payment_date,
                    description=desc,
                    line_total=None,
                    line_paid=amt,
                    balance_after=balance,
                    payment_method_label=method_label,
                )
            )
    return rows


def total_paid_for_receipt(record) -> Decimal:
    """Canonical total paid — matches service record, never double-counts ledger rows."""
    paid = record.paid_amount or Decimal("0")
    total_due = _total_due(record)
    if paid > total_due:
        return total_due
    if paid < Decimal("0"):
        return Decimal("0")
    return paid


def record_opening_ledger_entry(record, *, recorded_by=None):
    """Create the opening row when a service is first saved (idempotent)."""
    return ensure_opening_ledger_entry(record, recorded_by=recorded_by)


def record_initial_service_payments(record, *, recorded_by=None):
    """Log initial payment only when no opening row captures it."""
    if record.payment_entries.filter(entry_type=ServiceRecordPayment.ENTRY_PAYMENT).exists():
        return
    if record.payment_entries.filter(entry_type=ServiceRecordPayment.ENTRY_OPENING).exists():
        return
    paid = record.paid_amount or Decimal("0")
    if paid <= Decimal("0"):
        return

    payment_date = record.transaction_date or timezone.localdate()
    cc_total = record.credit_card_fee or Decimal("0")
    total = _total_due(record)
    balance = total - paid
    if balance < Decimal("0"):
        balance = Decimal("0")

    if record.payment_method_2 and (record.paid_amount_2 or Decimal("0")) > Decimal("0"):
        amt2 = record.paid_amount_2 or Decimal("0")
        amt1 = paid - amt2
        cc1 = (cc_total * amt1 / paid).quantize(Decimal("0.01")) if paid else Decimal("0")
        cc2 = cc_total - cc1
        if amt1 > Decimal("0"):
            ServiceRecordPayment.objects.create(
                service_record=record,
                entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
                amount=amt1,
                line_paid=amt1,
                balance_after=balance,
                payment_method=normalize_payment_method(record.payment_method),
                payment_date=payment_date,
                cc_fee=cc1,
                notes="Initial payment",
                recorded_by=recorded_by,
            )
        ServiceRecordPayment.objects.create(
            service_record=record,
            entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
            amount=amt2,
            line_paid=amt2,
            balance_after=balance,
            payment_method=normalize_payment_method(record.payment_method_2),
            payment_date=payment_date,
            cc_fee=cc2,
            notes="Initial payment",
            recorded_by=recorded_by,
        )
        reconcile_ledger_balances(record)
        return

    ServiceRecordPayment.objects.create(
        service_record=record,
        entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
        amount=paid,
        line_paid=paid,
        balance_after=balance,
        payment_method=normalize_payment_method(record.payment_method),
        payment_date=payment_date,
        cc_fee=cc_total,
        notes="Initial payment",
        recorded_by=recorded_by,
    )
    reconcile_ledger_balances(record)


def log_balance_payment(
    record,
    amount,
    payment_method,
    *,
    payment_date=None,
    recorded_by=None,
    notes="Balance payment",
):
    """Append a follow-up payment row (caller updates paid_amount on the record first)."""
    if amount <= Decimal("0"):
        return None
    when = parse_payment_date(payment_date)
    entry = ServiceRecordPayment.objects.create(
        service_record=record,
        entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
        amount=amount,
        line_paid=amount,
        balance_after=Decimal("0"),
        payment_method=normalize_payment_method(payment_method),
        payment_date=when,
        cc_fee=Decimal("0"),
        notes=notes,
        recorded_by=recorded_by,
    )
    reconcile_ledger_balances(record)
    return entry


def get_receipt_payment_entries(service_record):
    """Legacy helper — returns raw ORM entries."""
    return list(
        service_record.payment_entries.order_by("payment_date", "created_at", "id")
    )


# Backward-compatible alias
def total_paid_from_entries(entries):
    """Deprecated: use total_paid_for_receipt(record) instead."""
    total = Decimal("0")
    for entry in entries:
        if getattr(entry, "entry_type", "") == ServiceRecordPayment.ENTRY_OPENING:
            continue
        total += entry.amount or Decimal("0")
    return total
