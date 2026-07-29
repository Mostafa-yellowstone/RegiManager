from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0154_mobile_push_device"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="insurance_company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="daily_payment_transactions",
                to="core.insurancecompany",
            ),
        ),
    ]
