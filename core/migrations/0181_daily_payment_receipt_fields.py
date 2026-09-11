from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0180_daily_payment_policy_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="coverage",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Coverage type shown on the payment receipt (e.g. Liability, Owned).",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="next_payment_due",
            field=models.DateField(
                blank=True,
                help_text="Next installment due date shown on the receipt.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="next_payment_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Next installment amount shown on the receipt.",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="remaining_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Remaining balance shown on the receipt.",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="remaining_payments",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Number of remaining payments shown on the receipt.",
                null=True,
            ),
        ),
    ]
