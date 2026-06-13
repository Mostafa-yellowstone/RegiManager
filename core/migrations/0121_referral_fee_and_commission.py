from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0120_sitenews_organization_and_read_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="referral",
            name="referral_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Per-service fee paid to this referral partner, deducted from processing fee profit.",
                max_digits=10,
            ),
        ),
        migrations.AddField(
            model_name="servicerecord",
            name="referral_commission",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Referral partner share deducted from processing fee for this service.",
                max_digits=10,
            ),
        ),
    ]
