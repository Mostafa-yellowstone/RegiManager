import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0148_tlc_referred_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancecompany",
            name="broker_arrangement",
            field=models.CharField(
                blank=True,
                choices=[("br", "BR — Take broker fees"), ("bc", "BC — No broker fees")],
                default="",
                help_text="BR = take broker fees; BC = do not take broker fees.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="insurancecompany",
            name="license_alert_days",
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text="Show a renewal alert this many days before the license expires.",
            ),
        ),
        migrations.AddField(
            model_name="insurancecompany",
            name="license_effective_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="insurancecompany",
            name="license_expiration_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="insurancecompany",
            name="license_number",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AlterField(
            model_name="notification",
            name="client",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications",
                to="core.client",
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="insurance_company",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications",
                to="core.insurancecompany",
            ),
        ),
    ]
