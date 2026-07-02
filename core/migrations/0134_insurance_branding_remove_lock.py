from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0133_organization_insurance_review_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="insurance_intake_display_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Public name shown on the insurance intake portal (e.g. Xpress Insurance Solutions). Falls back to PSB name.",
                max_length=160,
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="insurance_intake_tagline",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Subtitle shown under the name on the public insurance intake portal.",
                max_length=255,
            ),
        ),
        migrations.RemoveField(
            model_name="organization",
            name="insurance_space_locked",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="insurance_space_password",
        ),
    ]
