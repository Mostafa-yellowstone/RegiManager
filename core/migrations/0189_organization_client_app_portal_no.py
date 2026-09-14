# Generated manually for Organization.client_app_portal_no

from django.db import migrations, models
from django.utils.crypto import get_random_string


def backfill_portal_nos(apps, schema_editor):
    Organization = apps.get_model("core", "Organization")
    used = set(
        Organization.objects.exclude(client_app_portal_no__isnull=True)
        .exclude(client_app_portal_no="")
        .values_list("client_app_portal_no", flat=True)
    )
    for org in Organization.objects.filter(
        models.Q(client_app_portal_no__isnull=True) | models.Q(client_app_portal_no="")
    ).iterator():
        for _ in range(40):
            candidate = get_random_string(6, allowed_chars="23456789")
            if candidate not in used:
                used.add(candidate)
                org.client_app_portal_no = candidate
                org.save(update_fields=["client_app_portal_no"])
                break


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0188_servicedocument_registration_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="client_app_portal_no",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Short code clients type in the wallet app (e.g. 482917). Separate from the long intake portal_token.",
                max_length=12,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(backfill_portal_nos, migrations.RunPython.noop),
    ]
