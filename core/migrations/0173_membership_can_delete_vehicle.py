from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0172_regiconnect_foundation"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationmembership",
            name="can_delete_vehicle",
            field=models.BooleanField(
                default=False,
                help_text="Can this agent remove vehicles from a client profile?",
            ),
        ),
        migrations.AlterField(
            model_name="servicedocument",
            name="custom_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional display title for this document (overrides the type label when set).",
                max_length=150,
            ),
        ),
    ]
