"""Payment ledger helpers for service receipts (transmittal / outstanding balances)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from .models import ServiceRecord, ServiceRecordPayment

PAYMENT_METHOD_KEYS = frozenset(dict(ServiceRecord.PAYMENT_METHODS).keys())
OPENING_DESCRIPTION = "Initial payment"
INITIAL_PAYMENT_NOTE = "Initial payment"


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


def record_payment_method_labels(record) -> str:
    """Human-readable method label(s) for receipt rows (no dollar amounts)."""
    m1 = payment_method_label(record.payment_method)
    if record.payment_method_2 and (record.paid_amount_2 or Decimal("0")) > Decimal("0"):
        m2 = payment_method_label(record.payment_method_2)
        return f"{m1} / {m2}"
    return m1


def format_receipt_row_description(method_label, base_description: str) -> str:
    """Prefix payment method when it is not already in the description text."""
    base = (base_description or "Payment").strip()
    label = (method_label or "").strip()
    if not label:
        return base
    if label.lower() in base.lower():
        return base
    return f"{label} — {base}"


def receipt_summary_description(record) -> str:
    """Description for the pre-hub summary row on the receipt PDF."""
    paid = total_paid_for_receipt(record)
    if paid <= Decimal("0"):
        return "—"
    total = _total_due(record)
    base = OPENING_DESCRIPTION if paid < total else "Payment"
    return format_receipt_row_description(record_payment_method_labels(record), base)


def parse_payment_date(value, default=None):
    """Parse YYYY-MM-DD from form input; fall back to default (usually today)."""
    from datetime import date as date_cls

    default = default or timezone.localdate()
    if isinstance(value, date_cls):
        return value
    raw = (value or "").strip()
    if not raw:
        return default
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return default


def _total_due(record):
    return record.service_fee or Decimal("0")


def has_follow_up_balance_payments(record) -> bool:
    """True when at least one payment was logged via Outstanding Balances or referral hub."""
    return record.payment_entries.filter(
        entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
    ).exclude(notes=INITIAL_PAYMENT_NOTE).exists()


def receipt_should_show_ledger(record) -> bool:
    """Detailed ledger rows (opening + follow-ups) appear after hub/referral balance payments."""
    return has_follow_up_balance_payments(record)


def receipt_outstanding_balance(record) -> Decimal:
    """Outstanding balance for receipt totals when ledger rows are not shown yet."""
    from .transaction_amounts import compute_referral_balance

    return compute_referral_balance(_total_due(record), total_paid_for_receipt(record))


def reset_ledger_after_edit(record) -> bool:
    """
    Wipe payment ledger on receipt edit so the PDF reflects the amended transaction.
    Preserves ledger when follow-up balance payments were made from the hub.
    """
    if has_follow_up_balance_payments(record):
        return False
    record.payment_entries.all().delete()
    return True


def _needs_opening_row(record):
    total = _total_due(record)
    paid = record.paid_amount or Decimal("0")
    return (
        record.transaction_type == "transmittal"
        or paid != total
    )


def _initial_paid_at_creation(record):
    """Down payment captured on the transaction date — not follow-up balance payments."""
    opening = record.payment_entries.filter(
        entry_type=ServiceRecordPayment.ENTRY_OPENING
    ).first()
    if opening and opening.line_paid is not None:
        return opening.line_paid

    legacy_initial = (
        record.payment_entries.filter(
            entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
            notes=INITIAL_PAYMENT_NOTE,
        )
        .order_by("payment_date", "created_at", "id")
        .first()
    )
    if legacy_initial:
        return legacy_initial.amount or Decimal("0")

    payment_sum = Decimal("0")
    for entry in record.payment_entries.filter(
        entry_type=ServiceRecordPayment.ENTRY_PAYMENT
    ):
        payment_sum += entry.amount or Decimal("0")

    paid = record.paid_amount or Decimal("0")
    initial_paid = paid - payment_sum
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
        has_follow_up = has_follow_up_balance_payments(record)
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
        notes=OPENING_DESCRIPTION,
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
    qs.filter(notes=INITIAL_PAYMENT_NOTE).delete()

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
            balance = total_due - cumulative_paid
            updates = {}
            if entry.line_total != total_due:
                updates["line_total"] = total_due
            if entry.balance_after != balance:
                updates["balance_after"] = balance
            if updates:
                ServiceRecordPayment.objects.filter(pk=entry.pk).update(**updates)
        else:
            amt = entry.amount or Decimal("0")
            if entry.entry_type == ServiceRecordPayment.ENTRY_REFUND:
                cumulative_paid -= amt
            else:
                cumulative_paid += amt
            balance = total_due - cumulative_paid
            if entry.balance_after != balance:
                ServiceRecordPayment.objects.filter(pk=entry.pk).update(
                    balance_after=balance
                )


def compute_ledger_rows(record) -> list[LedgerDisplayRow]:
    """Build display rows with correct running outstanding balance."""
    if not receipt_should_show_ledger(record):
        return []
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
            cumulative_paid = opening_paid
            balance = total_due - cumulative_paid
            rows.append(
                LedgerDisplayRow(
                    entry=entry,
                    is_opening=True,
                    payment_date=entry.payment_date,
                    description=format_receipt_row_description(
                        method_label, OPENING_DESCRIPTION
                    ),
                    line_total=entry.line_total or total_due,
                    line_paid=opening_paid,
                    balance_after=balance,
                    payment_method_label=method_label,
                )
            )
        else:
            amt = entry.amount or Decimal("0")
            if entry.entry_type == ServiceRecordPayment.ENTRY_REFUND:
                cumulative_paid -= amt
            else:
                cumulative_paid += amt
            balance = total_due - cumulative_paid
            desc = format_receipt_row_description(
                method_label,
                (entry.notes or "Payment").strip(),
            )
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
    """Canonical total paid shown on the receipt."""
    paid = record.paid_amount or Decimal("0")
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
                notes=INITIAL_PAYMENT_NOTE,
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
            notes=INITIAL_PAYMENT_NOTE,
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
        notes=INITIAL_PAYMENT_NOTE,
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
    """Append a follow-up payment row (caller updates paid_amount on the record after)."""
    if amount <= Decimal("0"):
        return None
    ensure_opening_ledger_entry(record, recorded_by=recorded_by)
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


def log_refund_payment(
    record,
    amount,
    *,
    payment_method=None,
    payment_date=None,
    recorded_by=None,
    notes="Refund issued",
):
    """Append a refund row and reduce the running paid balance on the original receipt."""
    if amount <= Decimal("0"):
        return None
    ensure_opening_ledger_entry(record, recorded_by=recorded_by)
    when = parse_payment_date(payment_date, default=record.transaction_date)
    entry = ServiceRecordPayment.objects.create(
        service_record=record,
        entry_type=ServiceRecordPayment.ENTRY_REFUND,
        amount=amount,
        line_paid=amount,
        balance_after=Decimal("0"),
        payment_method=normalize_payment_method(payment_method or record.payment_method),
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
