import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0199_ensure_pulse_query_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DirectoryEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("company", "Company"), ("shared_account", "Shared account"), ("person", "Person"), ("other", "Other")], default="company", max_length=30)),
                ("name", models.CharField(max_length=200)),
                ("category", models.CharField(blank=True, default="", help_text="Short label such as carrier, Gmail, or vendor.", max_length=120)),
                ("website", models.URLField(blank=True, default="")),
                ("portal_url", models.URLField(blank=True, default="")),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("address", models.CharField(blank=True, default="", max_length=300)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_directory_entries", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="directory_entries", to="core.organization")),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="directory_entries", to="core.space")),
            ],
            options={"ordering": ["name", "id"]},
        ),
        migrations.CreateModel(
            name="DirectoryPhone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(help_text="Who or what this line is, such as Claims or Maria.", max_length=120)),
                ("number", models.CharField(max_length=40)),
                ("extension", models.CharField(blank=True, default="", max_length=20)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="phones", to="core.directoryentry")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="DirectoryCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(help_text="Gmail, carrier portal, shared inbox, and so on.", max_length=120)),
                ("username", models.CharField(blank=True, default="", max_length=200)),
                ("secret", models.CharField(blank=True, default="", max_length=400)),
                ("login_url", models.URLField(blank=True, default="")),
                ("notes", models.CharField(blank=True, default="", max_length=300)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="credentials", to="core.directoryentry")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
