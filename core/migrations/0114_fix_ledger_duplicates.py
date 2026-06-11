from decimal import Decimal

from django.db import migrations


def fix_ledger_duplicates_and_balances(apps, schema_editor):
    ServiceRecord = apps.get_model("core", "ServiceRecord")
    ServiceRecordPayment = apps.get_model("core", "ServiceRecordPayment")

    for record in ServiceRecord.objects.iterator():
        opening = ServiceRecordPayment.objects.filter(
            service_record_id=record.id,
            entry_type="opening",
        ).first()
        if not opening:
            continue

        ServiceRecordPayment.objects.filter(
            service_record_id=record.id,
            entry_type="payment",
            notes="Initial payment",
        ).delete()

        opening_paid = opening.line_paid or Decimal("0")
        if opening_paid > Decimal("0"):
            ServiceRecordPayment.objects.filter(
                service_record_id=record.id,
                entry_type="payment",
                amount=opening_paid,
                payment_date=opening.payment_date,
            ).delete()

        total_due = record.service_fee or Decimal("0")
        cumulative = Decimal("0")
        for entry in ServiceRecordPayment.objects.filter(
            service_record_id=record.id
        ).order_by("payment_date", "created_at", "id"):
            if entry.entry_type == "opening":
                cumulative = min(entry.line_paid or Decimal("0"), total_due)
                balance = total_due - cumulative
                ServiceRecordPayment.objects.filter(pk=entry.pk).update(
                    line_total=total_due,
                    balance_after=max(balance, Decimal("0")),
                )
            else:
                cumulative = min(
                    cumulative + (entry.amount or Decimal("0")),
                    total_due,
                )
                balance = total_due - cumulative
                ServiceRecordPayment.objects.filter(pk=entry.pk).update(
                    balance_after=max(balance, Decimal("0")),
                )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0113_servicerecordpayment_opening_ledger"),
    ]

    operations = [
        migrations.RunPython(fix_ledger_duplicates_and_balances, migrations.RunPython.noop),
    ]
