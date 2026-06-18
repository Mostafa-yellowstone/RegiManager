from django.db import migrations, models


def migrate_commission_to_banking(apps, schema_editor):
    OrganizationMembership = apps.get_model("core", "OrganizationMembership")
    OrganizationMembership.objects.filter(
        can_view_commission=True,
        can_view_banking=False,
    ).update(can_view_banking=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0127_clientintake_insurance_monthly_payment"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationmembership",
            name="profile_photo",
            field=models.ImageField(
                blank=True,
                help_text="Profile photo shown in the portal menu, team management, and agent auditing.",
                null=True,
                upload_to="agent_profiles/",
            ),
        ),
        migrations.AlterField(
            model_name="organizationmembership",
            name="can_view_banking",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Can this agent access Banking & Companies in the insurance space, "
                    "manage commission fields, and mark daily bank payments as cleared?"
                ),
            ),
        ),
        migrations.RunPython(migrate_commission_to_banking, migrations.RunPython.noop),
    ]
