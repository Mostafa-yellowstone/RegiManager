import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0225_expense_watch_settings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="QuoteJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(max_length=16)),
                ("line", models.CharField(max_length=40)),
                ("jurisdiction", models.CharField(max_length=2)),
                ("status", models.CharField(max_length=32)),
                ("applicant_label", models.CharField(blank=True, default="", max_length=200)),
                ("intake", models.JSONField(blank=True, default=dict)),
                ("missing", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ny_auto_quote_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ny_auto_quote_jobs",
                        to="core.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "NY auto quote job",
                "verbose_name_plural": "NY auto quote jobs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="QuoteAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("carrier_key", models.CharField(max_length=40)),
                ("carrier_name", models.CharField(max_length=120)),
                ("status", models.CharField(max_length=32)),
                ("blocker_code", models.CharField(blank=True, default="", max_length=64)),
                ("detail", models.TextField(blank=True, default="")),
                ("missing", models.JSONField(blank=True, default=list)),
                ("quote_number", models.CharField(blank=True, default="", max_length=64)),
                ("term_premium", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("term_months", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("source", models.CharField(blank=True, default="", max_length=16)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attempts",
                        to="quoting.quotejob",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
