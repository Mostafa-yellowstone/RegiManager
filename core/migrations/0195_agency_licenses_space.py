import core.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0194_staff_space_and_permission"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AgencyLicenseFolder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("state_code", models.CharField(max_length=2)),
                ("state_name", models.CharField(max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agency_license_folders", to="core.organization")),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agency_license_folders", to="core.space")),
            ],
            options={"ordering": ["state_name"]},
        ),
        migrations.AddConstraint(
            model_name="agencylicensefolder",
            constraint=models.UniqueConstraint(fields=("organization", "state_code"), name="uniq_agency_license_folder_state"),
        ),
        migrations.CreateModel(
            name="AgencyLicense",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180)),
                ("license_number", models.CharField(blank=True, default="", max_length=80)),
                ("holder_name", models.CharField(blank=True, default="", max_length=180)),
                ("expiration_date", models.DateField(blank=True, null=True)),
                ("reminder_days", models.CharField(default="45,30,5", help_text="Comma-separated days before expiration, e.g. 45,30,5", max_length=80)),
                ("notes", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_agency_licenses", to=settings.AUTH_USER_MODEL)),
                ("folder", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="licenses", to="core.agencylicensefolder")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agency_licenses", to="core.organization")),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agency_licenses", to="core.space")),
            ],
            options={"ordering": ["expiration_date", "title"]},
        ),
        migrations.CreateModel(
            name="AgencyLicenseDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, default="", max_length=180)),
                ("file", models.FileField(upload_to=core.models.agency_license_upload_path)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("license", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documents", to="core.agencylicense")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agency_license_documents", to="core.organization")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="uploaded_agency_license_documents", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-uploaded_at"]},
        ),
    ]
