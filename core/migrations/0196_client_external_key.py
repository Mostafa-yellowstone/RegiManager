from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0195_agency_licenses_space"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="external_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Shared import key (Kintone unique column) that ties vehicles, transactions, and documents to this profile.",
                max_length=64,
            ),
        ),
        migrations.AddConstraint(
            model_name="client",
            constraint=models.UniqueConstraint(
                condition=models.Q(deleted_at__isnull=True) & ~models.Q(external_key=""),
                fields=("organization", "external_key"),
                name="uniq_client_external_key_per_org",
            ),
        ),
    ]
