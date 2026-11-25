import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0230_quote_lead_driver_and_limits"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="QuoteEngineJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("running", "Running"), ("waiting_otp", "Waiting for the login code"), ("done", "Done"), ("failed", "Failed")], db_index=True, default="running", max_length=20)),
                ("spend_approved", models.BooleanField(default=False)),
                ("otp_carrier", models.CharField(blank=True, default="", max_length=60)),
                ("otp_hint_email", models.CharField(blank=True, default="", help_text="Display only: where the code is sent.", max_length=200)),
                ("otp_code_enc", models.TextField(blank=True, default="")),
                ("otp_cancelled", models.BooleanField(default=False)),
                ("message", models.CharField(blank=True, default="", max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="engine_jobs", to="core.insurancequotelead")),
                ("run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="core.quoteenginerun")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
