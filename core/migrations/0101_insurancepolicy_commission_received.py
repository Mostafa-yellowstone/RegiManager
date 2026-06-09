from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0100_motorclub_space"),
    ]

    operations = [
        migrations.AddField(
            model_name="insurancepolicy",
            name="commission_received",
            field=models.BooleanField(
                default=False,
                help_text="When checked, this policy's commission counts toward Received Commission.",
            ),
        ),
    ]
