from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

import core.insurance_esign_models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0170_quote_lead_drop_new_default"),
    ]

    operations = [
        migrations.CreateModel(
            name="InsuranceESignEnvelope",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("original_file", models.FileField(upload_to=core.insurance_esign_models._original_upload_to)),
                ("signed_file", models.FileField(blank=True, upload_to=core.insurance_esign_models._signed_upload_to)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("awaiting", "Awaiting signature"),
                            ("signed", "Completed"),
                            ("void", "Void"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("fields_json", models.JSONField(blank=True, default=list)),
                ("audit_json", models.JSONField(blank=True, default=list)),
                ("signer_name", models.CharField(blank=True, default="", max_length=160)),
                ("signer_email", models.EmailField(blank=True, default="", max_length=254)),
                ("signer_token", models.CharField(db_index=True, max_length=64, unique=True)),
                ("signed_ip", models.CharField(blank=True, default="", max_length=45)),
                ("signed_user_agent", models.CharField(blank=True, default="", max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("signed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="insurance_esign_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurance_esign_envelopes",
                        to="core.organization",
                    ),
                ),
                (
                    "signed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="insurance_esign_signed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
