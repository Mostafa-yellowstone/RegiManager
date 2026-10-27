from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0215_insurance_forms_and_portals"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancecompany",
            name="quote_for_auto",
            field=models.BooleanField(
                default=False,
                help_text="Show this carrier when the team compares an auto quote.",
            ),
        ),
        migrations.AddField(
            model_name="insurancecompany",
            name="quote_for_commercial",
            field=models.BooleanField(
                default=False,
                help_text="Show this carrier when the team compares a commercial quote.",
            ),
        ),
    ]
