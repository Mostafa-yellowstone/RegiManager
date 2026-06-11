"""Payment ledger helpers for service receipts (transmittal / outstanding balances)."""

from datetime import date
from decimal import Decimal

from django.utils import timezone

from .models import ServiceRecord, ServiceRecordPayment

PAYMENT_METHOD_KEYS = frozenset(dict(ServiceRecord.PAYMENT_METHODS).keys())


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


def record_opening_ledger_entry(record, *, recorded_by=None):
    """
    First row in payment history: original transaction date, total due,
    amount paid at creation, and outstanding balance.
    """
    if record.payment_entries.filter(entry_type=ServiceRecordPayment.ENTRY_OPENING).exists():
        return

    total = record.service_fee or Decimal("0")
    paid = record.paid_amount or Decimal("0")
    balance = total - paid
    if balance < Decimal("0"):
        balance = Decimal("0")

    needs_opening = (
        record.transaction_type == "transmittal"
        or balance > Decimal("0")
        or paid < total
    )
    if not needs_opening:
        return

    txn_label = _transaction_label(record)
    ServiceRecordPayment.objects.create(
        service_record=record,
        entry_type=ServiceRecordPayment.ENTRY_OPENING,
        amount=Decimal("0"),
        line_total=total,
        line_paid=paid,
        balance_after=balance,
        payment_method=normalize_payment_method(record.payment_method),
        payment_date=record.transaction_date or timezone.localdate(),
        cc_fee=Decimal("0"),
        notes=f"{txn_label} — outstanding balance",
        recorded_by=recorded_by,
    )


def record_initial_service_payments(record, *, recorded_by=None):
    """Log amount paid when the service is first created (idempotent)."""
    if record.payment_entries.filter(entry_type=ServiceRecordPayment.ENTRY_PAYMENT).exists():
        return
    if record.payment_entries.filter(entry_type=ServiceRecordPayment.ENTRY_OPENING).exists():
        return
    paid = record.paid_amount or Decimal("0")
    if paid <= Decimal("0"):
        return

    payment_date = record.transaction_date or timezone.localdate()
    cc_total = record.credit_card_fee or Decimal("0")
    balance = record.service_fee - paid
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


def log_balance_payment(
    record,
    amount,
    payment_method,
    *,
    payment_date=None,
    recorded_by=None,
    notes="Balance payment",
):
    """Append a follow-up payment row (caller updates paid_amount on the record)."""
    if amount <= Decimal("0"):
        return None
    when = parse_payment_date(payment_date)
    balance = record.referral_balance or Decimal("0")
    if balance < Decimal("0"):
        balance = Decimal("0")
    return ServiceRecordPayment.objects.create(
        service_record=record,
        entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
        amount=amount,
        line_paid=amount,
        balance_after=balance,
        payment_method=normalize_payment_method(payment_method),
        payment_date=when,
        cc_fee=Decimal("0"),
        notes=notes,
        recorded_by=recorded_by,
    )


def get_receipt_payment_entries(service_record):
    """Ordered ledger lines for receipt rendering."""
    entries = list(
        service_record.payment_entries.order_by("payment_date", "created_at", "id")
    )
    if entries:
        return entries

    paid = service_record.paid_amount or Decimal("0")
    total = service_record.service_fee or Decimal("0")
    balance = total - paid
    if balance < Decimal("0"):
        balance = Decimal("0")

    if paid <= Decimal("0") and balance <= Decimal("0"):
        return []

    dt = service_record.transaction_date or service_record.created_at.date()

    class _LegacyEntry:
        def __init__(self):
            self.entry_type = ServiceRecordPayment.ENTRY_PAYMENT
            self.amount = paid
            self.line_total = None
            self.line_paid = paid
            self.balance_after = balance
            self.cc_fee = service_record.credit_card_fee or Decimal("0")
            self.payment_method = service_record.payment_method
            self.notes = "Payment"
            self.payment_date = dt

        def get_payment_method_display(self):
            return payment_method_label(self.payment_method)

        @property
        def is_opening(self):
            return False

        @property
        def display_paid(self):
            return self.amount

    return [_LegacyEntry()]


def total_paid_from_entries(entries):
    """Sum all money paid (opening down payment + follow-up payment rows)."""
    total = Decimal("0")
    for entry in entries:
        if getattr(entry, "is_opening", False) or getattr(entry, "entry_type", "") == ServiceRecordPayment.ENTRY_OPENING:
            total += entry.line_paid or Decimal("0")
        else:
            total += entry.display_paid if hasattr(entry, "display_paid") else (entry.amount or Decimal("0"))
    return total
