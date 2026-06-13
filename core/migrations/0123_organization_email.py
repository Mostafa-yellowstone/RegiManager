from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0122_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="PSB contact email printed on service receipts below the license number.",
                max_length=254,
            ),
        ),
    ]
