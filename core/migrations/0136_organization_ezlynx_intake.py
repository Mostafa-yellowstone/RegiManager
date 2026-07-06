from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0135_organization_business_owner_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="insurance_ezlynx_quote_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="EZLynx / AgentInsure consumer quoting URL to embed on the public insurance portal.",
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="insurance_intake_portal_mode",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Leave blank to auto-select: EZLynx dual capture when a quote URL is set, otherwise the native form.",
                max_length=20,
            ),
        ),
    ]
