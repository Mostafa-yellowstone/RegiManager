from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0164_quote_lead_vehicle_coverage_docs"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancequotelead",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="dl_number",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="vehicle_make",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="vehicle_model",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="vehicle_year",
            field=models.CharField(blank=True, default="", max_length=4),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="vin",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
    ]
