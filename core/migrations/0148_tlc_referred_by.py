from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0147_space_logo_branding"),
    ]

    operations = [
        migrations.AddField(
            model_name="tlcpolicy",
            name="referred_by",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Name of the person who referred this policy.",
                max_length=120,
            ),
        ),
    ]
