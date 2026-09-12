from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0184_client_app_access"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="app_pin_hash",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Hashed PIN for the client mobile app. Never store plaintext.",
                max_length=256,
            ),
        ),
    ]
