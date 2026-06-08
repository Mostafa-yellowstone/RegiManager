from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0092_daily_payment_transaction"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="is_cleared",
            field=models.BooleanField(default=False, help_text="Bank has cleared this payment"),
        ),
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="cleared_date",
            field=models.DateField(blank=True, help_text="Date the bank cleared the amount", null=True),
        ),
    ]
