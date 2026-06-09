from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0098_referral_and_insurance_type_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="vehicle",
            name="is_legacy_vin",
            field=models.BooleanField(
                default=False,
                help_text="Pre-1981 or non-standard VIN (fewer than 17 characters). Skips NHTSA decode.",
            ),
        ),
    ]
