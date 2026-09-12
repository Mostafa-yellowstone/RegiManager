from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0183_daily_payment_section_2119_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="app_access_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Allow this client to sign in to the mobile wallet app.",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="app_pin_hash",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Hashed PIN for the client mobile app. Never store plaintext.",
                max_length=128,
            ),
        ),
        migrations.CreateModel(
            name="ClientAppSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(db_index=True, max_length=64, unique=True)),
                ("device_label", models.CharField(blank=True, default="", max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="app_sessions",
                        to="core.client",
                    ),
                ),
            ],
            options={
                "verbose_name": "Client app session",
                "verbose_name_plural": "Client app sessions",
                "ordering": ["-created_at"],
            },
        ),
    ]
