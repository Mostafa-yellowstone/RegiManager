from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0155_daily_payment_insurance_company"),
    ]

    operations = [
        migrations.AddField(
            model_name="banktransaction",
            name="attachment",
            field=models.FileField(
                blank=True,
                help_text="Optional receipt, invoice, or supporting document.",
                null=True,
                upload_to="bank_transactions/%Y/%m/",
            ),
        ),
    ]
