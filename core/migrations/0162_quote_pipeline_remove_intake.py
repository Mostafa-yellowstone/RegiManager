# Generated manually for quote pipeline + remove InsuranceIntake

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0161_organization_roles"),
    ]

    operations = [
        migrations.CreateModel(
            name="InsuranceQuoteDistributionConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_auto_enabled", models.BooleanField(default=True)),
                (
                    "skip_sundays",
                    models.BooleanField(
                        default=True,
                        help_text="Pause auto-distribution on Sundays (America/New_York).",
                    ),
                ),
                (
                    "require_attendance_present",
                    models.BooleanField(
                        default=True,
                        help_text="Exclude agents with no open attendance check-in for the work day.",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "last_assigned_membership",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="core.organizationmembership",
                    ),
                ),
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quote_distribution_config",
                        to="core.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Quote distribution config",
                "verbose_name_plural": "Quote distribution configs",
            },
        ),
        migrations.CreateModel(
            name="InsuranceQuoteLead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("client_name", models.CharField(max_length=200)),
                ("phone", models.CharField(max_length=30)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("insurance_type", models.CharField(blank=True, default="", max_length=40)),
                ("has_prior", models.BooleanField(default=False)),
                ("is_experienced", models.BooleanField(default=False)),
                ("has_accident", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "stage",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("assigned", "Assigned"),
                            ("quoting", "Quoting"),
                            ("quoted", "Quoted"),
                            ("won", "Won"),
                            ("lost", "Lost"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=20,
                    ),
                ),
                ("assigned_at", models.DateTimeField(blank=True, null=True)),
                (
                    "assignment_mode",
                    models.CharField(
                        choices=[
                            ("auto", "Auto"),
                            ("manual", "Manual"),
                            ("unassigned", "Unassigned"),
                        ],
                        default="unassigned",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "agent_task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="quote_leads",
                        to="core.agenttask",
                    ),
                ),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="insurance_quote_leads",
                        to="core.organizationmembership",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="insurance_quote_leads_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurance_quote_leads",
                        to="core.organization",
                    ),
                ),
                (
                    "recommended_companies",
                    models.ManyToManyField(
                        blank=True,
                        related_name="recommended_on_quote_leads",
                        to="core.insurancecompany",
                    ),
                ),
            ],
            options={
                "verbose_name": "Insurance quote lead",
                "verbose_name_plural": "Insurance quote leads",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="InsuranceAgentOffDay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("off_date", models.DateField(db_index=True)),
                ("reason", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurance_off_days",
                        to="core.organizationmembership",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="insurance_agent_off_days",
                        to="core.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Insurance agent off day",
                "verbose_name_plural": "Insurance agent off days",
                "ordering": ["-off_date"],
            },
        ),
        migrations.AddIndex(
            model_name="insurancequotelead",
            index=models.Index(
                fields=["organization", "stage", "-created_at"],
                name="core_insura_organiz_quote_stg_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="insurancequotelead",
            index=models.Index(
                fields=["organization", "assigned_to", "-created_at"],
                name="core_insura_organiz_quote_asg_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="insuranceagentoffday",
            constraint=models.UniqueConstraint(
                fields=("membership", "off_date"),
                name="uniq_insurance_agent_off_day",
            ),
        ),
        migrations.DeleteModel(name="InsuranceIntake"),
    ]
