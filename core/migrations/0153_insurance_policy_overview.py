# Generated manually for insurance policy overview (vehicles / drivers).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0152_insurance_policy_dec_schedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancepolicy",
            name="named_insured",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Named insured from DEC (falls back to client name in overview).",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="insurancepolicy",
            name="insured_address",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="insurancepolicy",
            name="vin",
            field=models.CharField(blank=True, default="", max_length=17),
        ),
        migrations.AddField(
            model_name="insurancepolicy",
            name="plate_number",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="insurancepolicy",
            name="driver_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.CreateModel(
            name="InsurancePolicyVehicle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("auto_number", models.PositiveSmallIntegerField(default=1)),
                ("year", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("make", models.CharField(blank=True, default="", max_length=60)),
                ("vin", models.CharField(blank=True, default="", max_length=17)),
                ("plate_number", models.CharField(blank=True, default="", max_length=50)),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("expiration_date", models.DateField(blank=True, null=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="policy_vehicles",
                        to="core.insurancepolicy",
                    ),
                ),
            ],
            options={
                "ordering": ["auto_number"],
                "unique_together": {("policy", "auto_number")},
            },
        ),
        migrations.CreateModel(
            name="InsurancePolicyDriver",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("expiry_date", models.DateField(blank=True, null=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="policy_drivers",
                        to="core.insurancepolicy",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
    ]
