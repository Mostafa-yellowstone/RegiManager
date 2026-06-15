from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0126_vehicle_insurance_monthly_payment"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientintake",
            name="insurance_monthly_payment",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional monthly insurance payment",
                max_digits=10,
                null=True,
            ),
        ),
    ]
