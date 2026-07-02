# Generated manually for insurance intake feature

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0131_daily_payment_editor"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="is_public_insurance_intake_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Enable the public insurance intake portal and insurance agent intake queue.",
            ),
        ),
        migrations.CreateModel(
            name="InsuranceIntake",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending Review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("insurance_type", models.CharField(blank=True, default="", max_length=30)),
                ("source", models.CharField(default="walk_in", max_length=50)),
                ("business_type", models.CharField(default="new_business", max_length=50)),
                ("first_name", models.CharField(max_length=100)),
                ("last_name", models.CharField(max_length=100)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("phone_number", models.CharField(max_length=20)),
                ("dob", models.DateField(blank=True, null=True)),
                ("driver_license", models.CharField(blank=True, default="", max_length=50)),
                ("business_name", models.CharField(blank=True, default="", max_length=200)),
                ("business_ein", models.CharField(blank=True, default="", max_length=20)),
                ("dot_number", models.CharField(blank=True, default="", max_length=30)),
                ("fleet_vehicle_count", models.PositiveIntegerField(blank=True, null=True)),
                ("street_address", models.CharField(blank=True, default="", max_length=200)),
                ("city", models.CharField(blank=True, default="", max_length=100)),
                ("state", models.CharField(blank=True, default="NY", max_length=2)),
                ("zip_code", models.CharField(blank=True, default="", max_length=10)),
                ("vin", models.CharField(blank=True, default="", max_length=50)),
                ("year", models.IntegerField(blank=True, null=True)),
                ("make", models.CharField(blank=True, default="", max_length=100)),
                ("model", models.CharField(blank=True, default="", max_length=100)),
                ("current_carrier", models.CharField(blank=True, default="", max_length=150)),
                ("prior_policy_number", models.CharField(blank=True, default="", max_length=100)),
                ("requested_effective_date", models.DateField(blank=True, null=True)),
                ("intake_note", models.TextField(blank=True, default="")),
                (
                    "driver_license_file",
                    models.FileField(blank=True, null=True, upload_to="insurance_intake_docs/dl/"),
                ),
                (
                    "vehicle_registration_file",
                    models.FileField(blank=True, null=True, upload_to="insurance_intake_docs/registration/"),
                ),
                (
                    "other_docs_file",
                    models.FileField(blank=True, null=True, upload_to="insurance_intake_docs/other/"),
                ),
                ("additional_data", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_client",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="insurance_intakes",
                        to="core.client",
                    ),
                ),
                (
                    "created_policy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_intakes",
                        to="core.insurancepolicy",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurance_intakes",
                        to="core.organization",
                    ),
                ),
                (
                    "processed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="processed_insurance_intakes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Insurance Intake",
                "verbose_name_plural": "Insurance Intakes",
                "ordering": ["-created_at"],
            },
        ),
    ]
