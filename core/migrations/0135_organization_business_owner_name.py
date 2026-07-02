# Generated manually for business owner name on receipts.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0134_insurance_branding_remove_lock"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="business_owner_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Legal owner name(s) printed below the PSB business name on service receipts.",
                max_length=200,
            ),
        ),
    ]
