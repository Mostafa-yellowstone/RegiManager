from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0118_vehicle_body_type_suburban_pickup"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="is_public_intake_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Enable the public client intake portal and owner intake CRM for this PSB.",
            ),
        ),
    ]
