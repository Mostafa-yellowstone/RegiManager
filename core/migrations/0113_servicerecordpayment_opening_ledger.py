from decimal import Decimal

from django.db import migrations, models


def backfill_opening_rows(apps, schema_editor):
    ServiceRecord = apps.get_model("core", "ServiceRecord")
    ServiceRecordPayment = apps.get_model("core", "ServiceRecordPayment")

    for record in ServiceRecord.objects.iterator():
        if ServiceRecordPayment.objects.filter(
            service_record_id=record.id,
            entry_type="opening",
        ).exists():
            continue

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
            continue

        txn_label = "Transmittal" if record.transaction_type == "transmittal" else "Transaction"
        payment_date = record.transaction_date or (
            record.created_at.date() if record.created_at else None
        )
        if payment_date is None:
            continue

        ServiceRecordPayment.objects.create(
            service_record_id=record.id,
            entry_type="opening",
            amount=Decimal("0"),
            line_total=total,
            line_paid=paid,
            balance_after=balance,
            payment_method=record.payment_method or "cash",
            payment_date=payment_date,
            cc_fee=Decimal("0"),
            notes=f"{txn_label} — outstanding balance",
        )

        # Align balance_after on existing payment rows where missing
        payment_rows = ServiceRecordPayment.objects.filter(
            service_record_id=record.id,
            entry_type="payment",
        ).order_by("payment_date", "created_at", "id")

        running_paid = Decimal("0")
        for row in payment_rows:
            running_paid += row.amount or Decimal("0")
            row_balance = total - running_paid
            if row_balance < Decimal("0"):
                row_balance = Decimal("0")
            updates = {}
            if row.line_paid is None:
                updates["line_paid"] = row.amount
            if row.balance_after is None:
                updates["balance_after"] = row_balance
            if updates:
                ServiceRecordPayment.objects.filter(pk=row.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0112_servicerecordpayment"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicerecordpayment",
            name="entry_type",
            field=models.CharField(
                choices=[("opening", "Opening transaction"), ("payment", "Payment")],
                default="payment",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="servicerecordpayment",
            name="line_total",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Grand total at opening (opening rows only).",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="servicerecordpayment",
            name="line_paid",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Amount paid on this line (down payment or payment).",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="servicerecordpayment",
            name="balance_after",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Outstanding balance remaining after this line.",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="servicerecordpayment",
            name="amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.RunPython(backfill_opening_rows, migrations.RunPython.noop),
    ]
