from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0223_ezpass_client_documents"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="data",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Structured amounts shown as a breakdown in Pulse (premium, fees, commission).",
            ),
        ),
    ]
