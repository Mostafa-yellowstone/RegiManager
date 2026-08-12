from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0167_quote_lead_heard_about"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancequotelead",
            name="apartment",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="city",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="state",
            field=models.CharField(blank=True, default="NY", max_length=2),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="street_address",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="zip_code",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
    ]
