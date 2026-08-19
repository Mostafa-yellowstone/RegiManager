import django.db.models.deletion
import regiconnect.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0172_regiconnect_foundation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("regiconnect", "0001_regiconnect_foundation"),
    ]

    operations = [
        migrations.AddField(
            model_name="marketprofile",
            name="market_channel",
            field=models.CharField(
                choices=[("voluntary", "Voluntary"), ("assigned_risk", "Assigned Risk")],
                default="voluntary",
                help_text="Assigned Risk (e.g. NYAIP) is not a voluntary carrier the agent can shop like Progressive.",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="quoteleadconnectivity",
            name="quote_source",
            field=models.CharField(
                choices=[
                    ("manual", "Manual"),
                    ("regi_connect", "RegiConnect"),
                    ("regi_rater", "Regi Rater"),
                    ("carrier_api", "Carrier API"),
                    ("mga", "MGA"),
                    ("sftp", "SFTP"),
                    ("acord", "ACORD"),
                    ("other", "Other"),
                ],
                default="regi_connect",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="RatingRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("state", models.CharField(blank=True, default="", max_length=2)),
                ("line_of_business", models.CharField(blank=True, default="auto_personal", max_length=40)),
                ("effective_date", models.DateField(blank=True, null=True)),
                (
                    "transaction_type",
                    models.CharField(
                        choices=[
                            ("new_business", "New business"),
                            ("endorsement", "Endorsement"),
                            ("renewal", "Renewal"),
                        ],
                        default="new_business",
                        max_length=20,
                    ),
                ),
                (
                    "rating_mode",
                    models.CharField(
                        choices=[("real_time", "Real time"), ("async", "Asynchronous"), ("mixed", "Mixed")],
                        default="mixed",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("validating", "Validating"),
                            ("eligibility_check", "Eligibility check"),
                            ("ready", "Ready"),
                            ("rating", "Rating"),
                            ("partial_results", "Partial results"),
                            ("completed", "Completed"),
                            ("referred", "Referred"),
                            ("no_market", "No market"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                            ("expired", "Expired"),
                        ],
                        default="draft",
                        max_length=24,
                    ),
                ),
                ("canonical_snapshot", models.JSONField(blank=True, default=dict)),
                ("coverage", models.JSONField(blank=True, default=dict)),
                ("correlation_id", models.CharField(db_index=True, default=regiconnect.models._uuid, max_length=64)),
                ("idempotency_key", models.CharField(db_index=True, max_length=120)),
                ("last_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="regi_rater_requests",
                        to="core.client",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="regi_rater_requests_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="regi_rater_requests",
                        to="core.organization",
                    ),
                ),
                (
                    "quote_lead",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional link to the existing Quote Pipeline lead after select, or a seed lead.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="regi_rater_requests",
                        to="core.insurancequotelead",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="RatingJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("excluded", "Excluded"),
                            ("queued", "Queued"),
                            ("rating", "Rating"),
                            ("quoted", "Quoted"),
                            ("referred", "Referred"),
                            ("declined", "Declined"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                            ("expired", "Expired"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "eligibility",
                    models.CharField(
                        choices=[
                            ("eligible", "Eligible"),
                            ("ineligible", "Ineligible"),
                            ("refer", "Refer"),
                            ("unknown", "Unknown"),
                            ("unavailable", "Unavailable"),
                        ],
                        default="unknown",
                        max_length=20,
                    ),
                ),
                ("eligibility_reason", models.TextField(blank=True, default="")),
                ("error_category", models.CharField(blank=True, default="", max_length=40)),
                ("last_error", models.TextField(blank=True, default="")),
                ("correlation_id", models.CharField(db_index=True, default=regiconnect.models._uuid, max_length=64)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "connection",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rating_jobs",
                        to="regiconnect.connection",
                    ),
                ),
                (
                    "connector_job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rating_jobs",
                        to="regiconnect.connectorjob",
                    ),
                ),
                (
                    "market",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rating_jobs",
                        to="regiconnect.marketprofile",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="regi_rater_jobs",
                        to="core.organization",
                    ),
                ),
                (
                    "rating_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="jobs",
                        to="regiconnect.ratingrequest",
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rating_jobs",
                        to="regiconnect.submission",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="RatingExtension",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("extra", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "market",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rating_extensions",
                        to="regiconnect.marketprofile",
                    ),
                ),
                (
                    "rating_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extensions",
                        to="regiconnect.ratingrequest",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="RatingError",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("validation_error", "Validation"),
                            ("authentication_error", "Authentication"),
                            ("authorization_error", "Authorization"),
                            ("rate_limit", "Rate limit"),
                            ("timeout", "Timeout"),
                            ("carrier_error", "Carrier"),
                            ("unsupported", "Unsupported"),
                            ("decline", "Decline"),
                            ("referral", "Referral"),
                            ("system_error", "System"),
                            ("network_error", "Network"),
                        ],
                        default="system_error",
                        max_length=40,
                    ),
                ),
                ("message", models.TextField()),
                ("agent_message", models.TextField(blank=True, default="")),
                ("retryable", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="regi_rater_errors",
                        to="core.organization",
                    ),
                ),
                (
                    "rating_job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="errors",
                        to="regiconnect.ratingjob",
                    ),
                ),
                (
                    "rating_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="errors",
                        to="regiconnect.ratingrequest",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="canonicalquote",
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name="canonicalquote",
            name="status",
            field=models.CharField(
                choices=[
                    ("received", "Received"),
                    ("quoted", "Quoted"),
                    ("updated", "Updated"),
                    ("referred", "Referred"),
                    ("declined", "Declined"),
                    ("error", "Error"),
                    ("expired", "Expired"),
                    ("selected", "Selected"),
                    ("bound", "Bound"),
                    ("cancelled", "Cancelled"),
                ],
                default="received",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="canonicalquote",
            name="submission",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="quotes",
                to="regiconnect.submission",
            ),
        ),
        migrations.AddField(
            model_name="canonicalquote",
            name="connection",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="quotes",
                to="regiconnect.connection",
            ),
        ),
        migrations.AddField(
            model_name="canonicalquote",
            name="environment",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="canonicalquote",
            name="mapping_version",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="canonicalquote",
            name="premium_class",
            field=models.CharField(
                choices=[
                    ("estimated", "Estimated"),
                    ("indicative", "Indicative"),
                    ("final", "Final"),
                    ("bound", "Bound"),
                ],
                default="estimated",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="canonicalquote",
            name="provider_slug",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="canonicalquote",
            name="quote_source",
            field=models.CharField(
                choices=[
                    ("mock", "Mock / Test"),
                    ("direct_carrier", "Direct carrier"),
                    ("mga", "MGA"),
                    ("authorized_provider", "Authorized provider"),
                    ("ezlynx", "EZLynx (optional)"),
                    ("manual", "Manual"),
                    ("other", "Other"),
                ],
                default="other",
                help_text="Mock quotes must use MOCK and must never be shown as a carrier rate.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="canonicalquote",
            name="quoted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="canonicalquote",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="canonicalquote",
            name="rating_job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="quotes",
                to="regiconnect.ratingjob",
            ),
        ),
        migrations.AddField(
            model_name="canonicalquote",
            name="rating_request",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="quotes",
                to="regiconnect.ratingrequest",
            ),
        ),
        migrations.AddIndex(
            model_name="ratingrequest",
            index=models.Index(fields=["organization", "status", "-created_at"], name="regiconnect_rr_org_st_idx"),
        ),
        migrations.AddIndex(
            model_name="ratingrequest",
            index=models.Index(fields=["organization", "client"], name="regiconnect_rr_org_cl_idx"),
        ),
        migrations.AddConstraint(
            model_name="ratingrequest",
            constraint=models.UniqueConstraint(
                fields=("organization", "idempotency_key"),
                name="regiconnect_rating_request_idempotent",
            ),
        ),
        migrations.AddIndex(
            model_name="ratingjob",
            index=models.Index(fields=["organization", "status"], name="regiconnect_rj_org_st_idx"),
        ),
        migrations.AddConstraint(
            model_name="ratingjob",
            constraint=models.UniqueConstraint(
                fields=("rating_request", "market"),
                name="regiconnect_rating_job_request_market",
            ),
        ),
        migrations.AddConstraint(
            model_name="ratingextension",
            constraint=models.UniqueConstraint(
                fields=("rating_request", "market"),
                name="regiconnect_rating_extension_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="ratingerror",
            index=models.Index(fields=["organization", "rating_request"], name="regiconnect_re_org_rr_idx"),
        ),
        migrations.AddConstraint(
            model_name="canonicalquote",
            constraint=models.CheckConstraint(
                check=models.Q(("submission__isnull", False)) | models.Q(("rating_job__isnull", False)),
                name="regiconnect_quote_has_parent",
            ),
        ),
        migrations.AddConstraint(
            model_name="canonicalquote",
            constraint=models.UniqueConstraint(
                condition=models.Q(("submission__isnull", False)),
                fields=("submission", "version"),
                name="regiconnect_quote_submission_version",
            ),
        ),
        migrations.AddConstraint(
            model_name="canonicalquote",
            constraint=models.UniqueConstraint(
                condition=models.Q(("rating_job__isnull", False)),
                fields=("rating_job", "version"),
                name="regiconnect_quote_rating_job_version",
            ),
        ),
    ]
