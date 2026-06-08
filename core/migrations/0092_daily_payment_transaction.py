import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0091_add_custom_name_to_servicedocument"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancepolicy",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("cash", "Cash"),
                    ("zelle", "Zelle"),
                    ("credit_card", "Credit Card"),
                    ("checks", "Checks"),
                ],
                default="",
                help_text="How the broker fee was collected",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="DailyPaymentTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("transaction_date", models.DateField(db_index=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "payment_type",
                    models.CharField(
                        choices=[
                            ("new_business", "New Business"),
                            ("renewal", "Renewal"),
                            ("monthly_payment", "Monthly Payment"),
                            ("endorsement", "Endorsement"),
                            ("misc", "Misc"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "payment_method",
                    models.CharField(
                        choices=[
                            ("cash", "Cash"),
                            ("zelle", "Zelle"),
                            ("credit_card", "Credit Card"),
                            ("checks", "Checks"),
                        ],
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_payment_transactions",
                        to="core.client",
                    ),
                ),
                (
                    "insurance_policy",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="daily_payment_transactions",
                        to="core.insurancepolicy",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_payment_transactions",
                        to="core.organization",
                    ),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recorded_daily_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-transaction_date", "-created_at"],
            },
        ),
    ]
