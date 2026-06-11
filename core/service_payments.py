"""Payment ledger helpers for service receipts (transmittal / outstanding balances)."""

from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from .models import ServiceRecord, ServiceRecordPayment

PAYMENT_METHOD_KEYS = frozenset(dict(ServiceRecord.PAYMENT_METHODS).keys())


def normalize_payment_method(value):
    method = (value or "cash").strip()
    return method if method in PAYMENT_METHOD_KEYS else "cash"


def payment_method_label(method):
    return dict(ServiceRecord.PAYMENT_METHODS).get(method, method or "Cash")


def record_initial_service_payments(record, *, recorded_by=None):
    """Log amount paid when the service is first created (idempotent)."""
    if record.payment_entries.exists():
        return
    paid = record.paid_amount or Decimal("0")
    if paid <= Decimal("0"):
        return

    payment_date = record.transaction_date or timezone.localdate()
    cc_total = record.credit_card_fee or Decimal("0")

    if record.payment_method_2 and (record.paid_amount_2 or Decimal("0")) > Decimal("0"):
        amt2 = record.paid_amount_2 or Decimal("0")
        amt1 = paid - amt2
        cc1 = (cc_total * amt1 / paid).quantize(Decimal("0.01")) if paid else Decimal("0")
        cc2 = cc_total - cc1
        if amt1 > Decimal("0"):
            ServiceRecordPayment.objects.create(
                service_record=record,
                amount=amt1,
                payment_method=normalize_payment_method(record.payment_method),
                payment_date=payment_date,
                cc_fee=cc1,
                notes="Initial payment",
                recorded_by=recorded_by,
            )
        ServiceRecordPayment.objects.create(
            service_record=record,
            amount=amt2,
            payment_method=normalize_payment_method(record.payment_method_2),
            payment_date=payment_date,
            cc_fee=cc2,
            notes="Initial payment",
            recorded_by=recorded_by,
        )
        return

    ServiceRecordPayment.objects.create(
        service_record=record,
        amount=paid,
        payment_method=normalize_payment_method(record.payment_method),
        payment_date=payment_date,
        cc_fee=cc_total,
        notes="Initial payment",
        recorded_by=recorded_by,
    )


def log_balance_payment(record, amount, payment_method, *, recorded_by=None, notes="Balance payment"):
    """Append a follow-up payment row (caller updates paid_amount on the record)."""
    if amount <= Decimal("0"):
        return None
    return ServiceRecordPayment.objects.create(
        service_record=record,
        amount=amount,
        payment_method=normalize_payment_method(payment_method),
        payment_date=timezone.localdate(),
        cc_fee=Decimal("0"),
        notes=notes,
        recorded_by=recorded_by,
    )


def get_receipt_payment_entries(service_record):
    """Ordered payment lines for receipt rendering."""
    entries = list(
        service_record.payment_entries.order_by("payment_date", "created_at", "id")
    )
    if entries:
        return entries

    paid = service_record.paid_amount or Decimal("0")
    if paid <= Decimal("0"):
        return []

    dt = service_record.transaction_date or service_record.created_at.date()
    when = service_record.created_at
    if when is None:
        when = timezone.make_aware(datetime.combine(dt, datetime.min.time()))
    elif timezone.is_naive(when):
        when = timezone.make_aware(when, timezone.get_current_timezone())

    class _LegacyEntry:
        def __init__(self):
            self.amount = paid
            self.cc_fee = service_record.credit_card_fee or Decimal("0")
            self.payment_method = service_record.payment_method
            self.notes = "Payment"
            self.created_at = when
            self.payment_date = dt

        def get_payment_method_display(self):
            return payment_method_label(self.payment_method)

    return [_LegacyEntry()]
