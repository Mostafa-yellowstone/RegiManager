from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0158_agenttask_status_completion_note"),
    ]

    operations = [
        migrations.AlterField(
            model_name="insurancepolicy",
            name="source",
            field=models.CharField(
                choices=[
                    ("walk_in", "Walk-In"),
                    ("google_search", "Google Search"),
                    ("meta_platform", "Meta Platform"),
                    ("google_campaigns", "Google Campaigns"),
                    ("existing_client", "Existing Client"),
                    ("lost_client", "Lost Client"),
                    ("dealer", "Dealer"),
                    ("referral", "Referral"),
                    ("cold_calling", "Cold Calling"),
                ],
                default="walk_in",
                max_length=50,
            ),
        ),
    ]
