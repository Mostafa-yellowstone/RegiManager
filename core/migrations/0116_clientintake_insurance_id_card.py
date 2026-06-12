from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0115_backfill_missing_opening_rows"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientintake",
            name="insurance_id_card",
            field=models.FileField(
                blank=True,
                help_text="Insurance ID card (PDF only).",
                null=True,
                upload_to="intake_docs/insurance_id/",
            ),
        ),
    ]
