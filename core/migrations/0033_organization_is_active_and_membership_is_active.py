from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_organizationmembership_can_trigger_automation"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="is_active",
            field=models.BooleanField(default=True, help_text="Enable or disable this PSB account."),
        ),
        migrations.AddField(
            model_name="organizationmembership",
            name="is_active",
            field=models.BooleanField(default=True, help_text="Enable or disable this agent in this PSB."),
        ),
    ]
