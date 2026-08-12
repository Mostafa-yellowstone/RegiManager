from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0165_quote_lead_car_and_dl_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="InsuranceQuoteLeadDriver",
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
                ("full_name", models.CharField(blank=True, default="", max_length=200)),
                ("dl_number", models.CharField(blank=True, default="", max_length=40)),
                ("date_of_birth", models.DateField(blank=True, null=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "lead",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="additional_drivers",
                        to="core.insurancequotelead",
                    ),
                ),
            ],
            options={
                "verbose_name": "Quote lead additional driver",
                "verbose_name_plural": "Quote lead additional drivers",
                "ordering": ["sort_order", "id"],
            },
        ),
    ]
