from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0159_insurancepolicy_lost_client_source"),
    ]

    operations = [
        migrations.CreateModel(
            name="InsuranceMonthlyTarget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveIntegerField()),
                (
                    "month",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(12),
                        ]
                    ),
                ),
                ("premium_target", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("commission_target", models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=14)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurance_monthly_targets",
                        to="core.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Insurance monthly target",
                "verbose_name_plural": "Insurance monthly targets",
                "ordering": ["-year", "-month"],
            },
        ),
        migrations.CreateModel(
            name="InsuranceMarketPremiumAssumption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("insurance_type", models.CharField(db_index=True, max_length=50)),
                ("avg_premium", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurance_market_assumptions",
                        to="core.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Insurance market premium assumption",
                "verbose_name_plural": "Insurance market premium assumptions",
                "ordering": ["insurance_type"],
            },
        ),
        migrations.CreateModel(
            name="InsuranceLineTarget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("insurance_type", models.CharField(db_index=True, max_length=50)),
                ("premium_target", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("commission_target", models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=14)),
                (
                    "market_avg_premium",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Optional market assumption used by the planner for this month.",
                        max_digits=12,
                        null=True,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "monthly_target",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="line_targets",
                        to="core.insurancemonthlytarget",
                    ),
                ),
            ],
            options={
                "verbose_name": "Insurance line target",
                "verbose_name_plural": "Insurance line targets",
                "ordering": ["insurance_type"],
            },
        ),
        migrations.AddConstraint(
            model_name="insurancemonthlytarget",
            constraint=models.UniqueConstraint(
                fields=("organization", "year", "month"),
                name="uniq_insurance_monthly_target_org_ym",
            ),
        ),
        migrations.AddConstraint(
            model_name="insurancemarketpremiumassumption",
            constraint=models.UniqueConstraint(
                fields=("organization", "insurance_type"),
                name="uniq_insurance_market_assumption_org_type",
            ),
        ),
        migrations.AddConstraint(
            model_name="insurancelinetarget",
            constraint=models.UniqueConstraint(
                fields=("monthly_target", "insurance_type"),
                name="uniq_insurance_line_target_month_type",
            ),
        ),
    ]
