from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0171_insurance_esign"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationmembership",
            name="can_manage_regiconnect",
            field=models.BooleanField(
                default=False,
                help_text="Can this member manage appointments, connections, submissions, retries, and certification?",
            ),
        ),
        migrations.AddField(
            model_name="organizationmembership",
            name="can_view_regiconnect",
            field=models.BooleanField(
                default=False,
                help_text="Can this member view Markets & Access, Connectivity, and Submissions in Insurance Space?",
            ),
        ),
    ]
