from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0108_insurance_policy_endorsement_stage"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="psbc_license",
            field=models.CharField(
                blank=True,
                default="",
                help_text="PSB license number printed on service receipts under PSBC No.",
                max_length=60,
            ),
        ),
    ]
