from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0178_daily_payment_method_choices"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InsuranceSavedSignature",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                (
                    "image",
                    models.ImageField(
                        upload_to="insurance_esign/saved_signatures/%Y/%m/",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurance_saved_signatures",
                        to="core.organization",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurance_saved_signatures",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Insurance saved signature",
                "verbose_name_plural": "Insurance saved signatures",
                "ordering": ["name", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="insurancesavedsignature",
            constraint=models.UniqueConstraint(
                fields=("organization", "owner", "name"),
                name="uniq_insurance_saved_signature_name",
            ),
        ),
    ]
