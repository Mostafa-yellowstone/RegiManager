from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import core.insurance_quote_pipeline_models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0163_notification_action_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancequotelead",
            name="coverage_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("liability", "Liability only"),
                    ("full", "Full coverage"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="vehicle_ownership",
            field=models.CharField(
                blank=True,
                choices=[
                    ("blank", "Blank"),
                    ("owned", "Owned"),
                    ("financed", "Financed"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="InsuranceQuoteLeadDocument",
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
                (
                    "file",
                    models.FileField(
                        upload_to=core.insurance_quote_pipeline_models.quote_lead_document_upload_to
                    ),
                ),
                ("original_name", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "lead",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="core.insurancequotelead",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Quote lead document",
                "verbose_name_plural": "Quote lead documents",
                "ordering": ["created_at"],
            },
        ),
    ]
