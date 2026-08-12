from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0168_quote_lead_address"),
    ]

    operations = [
        migrations.CreateModel(
            name="InsuranceQuoteLeadVehicle",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("make", models.CharField(blank=True, default="", max_length=80)),
                ("model", models.CharField(blank=True, default="", max_length=80)),
                ("year", models.CharField(blank=True, default="", max_length=4)),
                ("vin", models.CharField(blank=True, default="", max_length=32)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "lead",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="additional_vehicles",
                        to="core.insurancequotelead",
                    ),
                ),
            ],
            options={
                "verbose_name": "Quote lead additional vehicle",
                "verbose_name_plural": "Quote lead additional vehicles",
                "ordering": ["sort_order", "id"],
            },
        ),
    ]
