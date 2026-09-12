from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0181_daily_payment_receipt_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="section_2119",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Section 2119 reference shown on new business / renewal receipts.",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="credit_card_fee",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional credit card fee; shown on the receipt only when greater than zero.",
                max_digits=12,
                null=True,
            ),
        ),
    ]
