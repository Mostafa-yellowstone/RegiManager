from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0176_remove_regiconnect"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancequotelead",
            name="dealer_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AlterField(
            model_name="insurancequotelead",
            name="heard_about",
            field=models.CharField(
                blank=True,
                choices=[
                    ("google_search", "Google Search"),
                    ("walk_in", "Walk-In"),
                    ("meta_platform", "Meta Platform"),
                    ("google_campaigns", "Google Campaigns"),
                    ("existing_client", "Existing Client"),
                    ("dealer", "Dealer"),
                    ("referral", "Referral"),
                    ("cold_calling", "Cold Calling"),
                    ("other", "Other"),
                ],
                default="",
                max_length=40,
            ),
        ),
    ]
