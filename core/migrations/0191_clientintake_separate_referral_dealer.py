from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0190_client_source_choices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clientintake",
            name="source",
            field=models.CharField(
                choices=[
                    ("google_search", "Google Search"),
                    ("walk_in", "Walk-In"),
                    ("website", "Website"),
                    ("meta_platform", "Meta Platform"),
                    ("google_campaigns", "Google Campaigns"),
                    ("existing_client", "Existing Client"),
                    ("lost_client", "Lost Client"),
                    ("dealer", "Dealer"),
                    ("referral", "Referral"),
                    ("cold_calling", "Cold Calling"),
                    ("other", "Other"),
                ],
                default="google_search",
                max_length=50,
            ),
        ),
    ]
