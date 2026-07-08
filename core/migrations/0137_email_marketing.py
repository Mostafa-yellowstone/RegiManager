import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0136_organization_ezlynx_intake"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationmembership",
            name="can_manage_email_marketing",
            field=models.BooleanField(
                default=False,
                help_text="Can this agent manage email marketing lists, CRM contacts, and campaigns?",
            ),
        ),
        migrations.CreateModel(
            name="EmailMarketingList",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True, default="")),
                ("accent_color", models.CharField(default="#2563eb", max_length=7)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="email_marketing_lists_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_marketing_lists",
                        to="core.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at", "name"],
                "unique_together": {("organization", "name")},
            },
        ),
        migrations.CreateModel(
            name="EmailCampaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("subject", models.CharField(blank=True, default="", max_length=255)),
                ("html_content", models.TextField(blank=True, default="")),
                ("css_content", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("sent", "Sent")],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("last_sent_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="email_campaigns_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "marketing_list",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="campaigns",
                        to="core.emailmarketinglist",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_campaigns",
                        to="core.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="EmailMarketingContact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("address_line1", models.CharField(blank=True, default="", max_length=200)),
                ("address_line2", models.CharField(blank=True, default="", max_length=200)),
                ("address_line3", models.CharField(blank=True, default="", max_length=200)),
                ("city", models.CharField(blank=True, default="", max_length=100)),
                ("state", models.CharField(blank=True, default="", max_length=2)),
                ("zip_code", models.CharField(blank=True, default="", max_length=10)),
                ("phone", models.CharField(blank=True, default="", max_length=30)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("website", models.URLField(blank=True, default="", max_length=500)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "marketing_list",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contacts",
                        to="core.emailmarketinglist",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_marketing_contacts",
                        to="core.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["name", "id"],
            },
        ),
        migrations.CreateModel(
            name="EmailMarketingAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="email_marketing/%Y/%m/")),
                ("label", models.CharField(blank=True, default="", max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "marketing_list",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assets",
                        to="core.emailmarketinglist",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_marketing_assets",
                        to="core.organization",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="EmailCampaignBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("filter_snapshot", models.JSONField(blank=True, default=dict)),
                ("recipient_count", models.PositiveIntegerField(default=0)),
                ("sent_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="batches",
                        to="core.emailcampaign",
                    ),
                ),
                (
                    "sent_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="EmailCampaignRecipient",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("error_message", models.TextField(blank=True, default="")),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recipient_logs",
                        to="core.emailcampaignbatch",
                    ),
                ),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recipient_logs",
                        to="core.emailcampaign",
                    ),
                ),
                (
                    "contact",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="core.emailmarketingcontact",
                    ),
                ),
            ],
            options={
                "ordering": ["-sent_at", "-id"],
            },
        ),
    ]
