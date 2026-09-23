# Staff space + can_manage_staff permission

import core.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0193_defense_driving_and_important_docs"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationmembership",
            name="can_manage_staff",
            field=models.BooleanField(
                default=False,
                help_text="Can this member manage Staff space employee profiles and documents?",
            ),
        ),
        migrations.CreateModel(
            name="StaffEmployee",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("first_name", models.CharField(max_length=80)),
                ("last_name", models.CharField(max_length=80)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("phone", models.CharField(blank=True, default="", max_length=40)),
                ("job_title", models.CharField(blank=True, default="", max_length=120)),
                ("department", models.CharField(blank=True, default="", max_length=120)),
                (
                    "employment_status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("on_leave", "On Leave"),
                            ("terminated", "Terminated"),
                        ],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("hire_date", models.DateField(blank=True, null=True)),
                ("date_of_birth", models.DateField(blank=True, null=True)),
                ("address", models.CharField(blank=True, default="", max_length=255)),
                ("city", models.CharField(blank=True, default="", max_length=80)),
                ("state", models.CharField(blank=True, default="", max_length=40)),
                ("zip_code", models.CharField(blank=True, default="", max_length=20)),
                (
                    "emergency_contact_name",
                    models.CharField(blank=True, default="", max_length=120),
                ),
                (
                    "emergency_contact_phone",
                    models.CharField(blank=True, default="", max_length=40),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "photo",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=core.models.staff_photo_upload_path,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_staff_employees",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "linked_user",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional link to a login user / agent account.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="staff_employee_profiles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_employees",
                        to="core.organization",
                    ),
                ),
                (
                    "space",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_employees",
                        to="core.space",
                    ),
                ),
            ],
            options={
                "ordering": ["last_name", "first_name"],
            },
        ),
        migrations.CreateModel(
            name="StaffDocument",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("cv", "CV / Resume"),
                            ("id", "ID / License"),
                            ("contract", "Contract"),
                            ("certificate", "Certificate"),
                            ("payroll", "Payroll"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=20,
                    ),
                ),
                (
                    "file",
                    models.FileField(upload_to=core.models.staff_document_upload_path),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "expires_at",
                    models.DateField(
                        blank=True,
                        help_text="Optional expiry for IDs, certificates, or work authorization.",
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="core.staffemployee",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_documents",
                        to="core.organization",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_staff_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
