from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0162_quote_pipeline_remove_intake"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="action_url",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Relative portal path opened when the user clicks this notification.",
                max_length=400,
            ),
        ),
    ]
