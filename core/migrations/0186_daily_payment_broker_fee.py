from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0185_client_app_pin_hash_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="broker_fee",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional broker fee; shown on the receipt only when greater than zero.",
                max_digits=12,
                null=True,
            ),
        ),
    ]
