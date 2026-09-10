from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0179_insurance_saved_signature"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="policy_number",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Policy number shown on the payment receipt.",
                max_length=100,
            ),
        ),
    ]
