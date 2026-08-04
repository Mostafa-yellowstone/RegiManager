from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0156_banktransaction_attachment"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailmarketingcontact",
            name="assigned_agent",
            field=models.ForeignKey(
                blank=True,
                help_text="Insurance agent this CRM lead was assigned to.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_email_leads",
                to="core.organizationmembership",
            ),
        ),
        migrations.AddField(
            model_name="emailmarketingcontact",
            name="assigned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailmarketingcontact",
            name="assigned_task",
            field=models.ForeignKey(
                blank=True,
                help_text="Latest portal task created from this CRM lead.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="email_marketing_contacts",
                to="core.agenttask",
            ),
        ),
    ]
