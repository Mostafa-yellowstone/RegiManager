from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0149_insurance_company_license"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="psbc_license_alert_days",
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text="Show a renewal alert this many days before the PSB license expires.",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="psbc_license_effective_date",
            field=models.DateField(
                blank=True,
                help_text="Date the PSB license became effective.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="psbc_license_expiration_date",
            field=models.DateField(
                blank=True,
                help_text="Date the PSB license expires.",
                null=True,
            ),
        ),
    ]
