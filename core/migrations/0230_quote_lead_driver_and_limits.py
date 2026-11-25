from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0229_quote_followup_steps"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancequotelead",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[("male", "Male"), ("female", "Female"), ("other", "Other")],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="effective_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="bodily_injury_limit",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
