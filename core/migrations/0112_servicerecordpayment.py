from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def backfill_service_payments(apps, schema_editor):
    ServiceRecord = apps.get_model("core", "ServiceRecord")
    ServiceRecordPayment = apps.get_model("core", "ServiceRecordPayment")

    for record in ServiceRecord.objects.filter(paid_amount__gt=0).iterator():
        if ServiceRecordPayment.objects.filter(service_record_id=record.id).exists():
            continue
        paid = record.paid_amount or Decimal("0")
        if paid <= Decimal("0"):
            continue
        payment_date = record.transaction_date or (
            record.created_at.date() if record.created_at else timezone.localdate()
        )
        cc_total = record.credit_card_fee or Decimal("0")

        if record.payment_method_2 and (record.paid_amount_2 or Decimal("0")) > Decimal("0"):
            amt2 = record.paid_amount_2 or Decimal("0")
            amt1 = paid - amt2
            cc1 = (cc_total * amt1 / paid).quantize(Decimal("0.01")) if paid else Decimal("0")
            cc2 = cc_total - cc1
            if amt1 > Decimal("0"):
                ServiceRecordPayment.objects.create(
                    service_record_id=record.id,
                    amount=amt1,
                    payment_method=record.payment_method or "cash",
                    payment_date=payment_date,
                    cc_fee=cc1,
                    notes="Initial payment",
                )
            ServiceRecordPayment.objects.create(
                service_record_id=record.id,
                amount=amt2,
                payment_method=record.payment_method_2 or "cash",
                payment_date=payment_date,
                cc_fee=cc2,
                notes="Initial payment",
            )
        else:
            ServiceRecordPayment.objects.create(
                service_record_id=record.id,
                amount=paid,
                payment_method=record.payment_method or "cash",
                payment_date=payment_date,
                cc_fee=cc_total,
                notes="Initial payment",
            )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0111_spacedocumentrecord_quantity"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceRecordPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("payment_method", models.CharField(
                    choices=[
                        ("cash", "Cash"),
                        ("zelle", "Zelle"),
                        ("checks", "Checks"),
                        ("visa", "Visa"),
                        ("mastercard", "Mastercard"),
                        ("discover", "Discover"),
                        ("diners_club", "Diners Club"),
                        ("american_express", "American Express"),
                    ],
                    default="cash",
                    max_length=50,
                )),
                ("payment_date", models.DateField(default=timezone.now)),
                ("cc_fee", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("recorded_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=models.deletion.SET_NULL,
                    related_name="recorded_service_payments",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("service_record", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="payment_entries",
                    to="core.servicerecord",
                )),
            ],
            options={
                "ordering": ["payment_date", "created_at", "id"],
            },
        ),
        migrations.RunPython(backfill_service_payments, migrations.RunPython.noop),
    ]
