from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0132_insurance_intake"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="insurance_show_review_button",
            field=models.BooleanField(
                default=False,
                help_text="Add a review button to the insurance intake completion page.",
                verbose_name="Show Review Button on Insurance Intake Success",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="insurance_review_link",
            field=models.URLField(
                blank=True,
                help_text="URL for the review button on the insurance intake success page.",
                max_length=500,
                null=True,
                verbose_name="Insurance Review Link",
            ),
        ),
    ]
