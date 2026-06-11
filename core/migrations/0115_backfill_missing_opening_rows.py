from decimal import Decimal

from django.db import migrations


def _total_due(record):
    return record.service_fee or Decimal("0")


def _needs_opening(record):
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


def _initial_paid(record, ServiceRecordPayment):
    initial = ServiceRecordPayment.objects.filter(
        service_record_id=record.id,
        entry_type="payment",
        notes="Initial payment",
    ).order_by("payment_date", "created_at", "id").first()
    if initial:
        return initial.amount or Decimal("0")

    follow_up_total = Decimal("0")
    for entry in ServiceRecordPayment.objects.filter(
        service_record_id=record.id,
        entry_type="payment",
    ).exclude(notes="Initial payment"):
        follow_up_total += entry.amount or Decimal("0")

    paid = record.paid_amount or Decimal("0")
    initial_paid = paid - follow_up_total
    if initial_paid < Decimal("0"):
        initial_paid = Decimal("0")
    return initial_paid


def backfill_missing_opening_rows(apps, schema_editor):
    ServiceRecord = apps.get_model("core", "ServiceRecord")
    ServiceRecordPayment = apps.get_model("core", "ServiceRecordPayment")

    for record in ServiceRecord.objects.iterator():
        if not _needs_opening(record):
            continue
        if ServiceRecordPayment.objects.filter(
            service_record_id=record.id,
            entry_type="opening",
        ).exists():
            continue

        total = _total_due(record)
        initial_paid = _initial_paid(record, ServiceRecordPayment)
        balance = total - initial_paid
        if balance < Decimal("0"):
            balance = Decimal("0")

        payment_date = record.transaction_date
        if payment_date is None and record.created_at:
            payment_date = record.created_at.date()
        if payment_date is None:
            continue

        txn_label = "Transmittal" if record.transaction_type == "transmittal" else "Transaction"
        ServiceRecordPayment.objects.create(
            service_record_id=record.id,
            entry_type="opening",
            amount=Decimal("0"),
            line_total=total,
            line_paid=initial_paid,
            balance_after=balance,
            payment_method=record.payment_method or "cash",
            payment_date=payment_date,
            cc_fee=Decimal("0"),
            notes=f"{txn_label} transaction",
        )

        ServiceRecordPayment.objects.filter(
            service_record_id=record.id,
            entry_type="payment",
            notes="Initial payment",
        ).delete()

        cumulative = Decimal("0")
        for entry in ServiceRecordPayment.objects.filter(
            service_record_id=record.id
        ).order_by("payment_date", "created_at", "id"):
            if entry.entry_type == "opening":
                cumulative = min(entry.line_paid or Decimal("0"), total)
            else:
                cumulative = min(
                    cumulative + (entry.amount or Decimal("0")),
                    total,
                )
            row_balance = total - cumulative
            if row_balance < Decimal("0"):
                row_balance = Decimal("0")
            ServiceRecordPayment.objects.filter(pk=entry.pk).update(
                balance_after=row_balance
            )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0114_fix_ledger_duplicates"),
    ]

    operations = [
        migrations.RunPython(backfill_missing_opening_rows, migrations.RunPython.noop),
    ]
