from django.db import migrations, models


def remap_legacy_member_roles(apps, schema_editor):
    OrganizationMembership = apps.get_model("core", "OrganizationMembership")
    for mem in OrganizationMembership.objects.filter(role="agent").iterator():
        if mem.can_deal_with_insurance:
            mem.role = "insurance_agent"
        else:
            mem.role = "agent"
        mem.save(update_fields=["role"])


def noop_reverse(apps, schema_editor):
    OrganizationMembership = apps.get_model("core", "OrganizationMembership")
    OrganizationMembership.objects.filter(
        role__in=["agent", "insurance_agent", "manager", "accountant"]
    ).exclude(role="owner").update(role="agent")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0160_insurance_targets_planner"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organizationmembership",
            name="role",
            field=models.CharField(
                choices=[
                    ("owner", "Owner"),
                    ("manager", "Manager"),
                    ("accountant", "Accountant"),
                    ("insurance_agent", "Insurance Agent"),
                    ("agent", "Agent"),
                    ("member", "Agent (legacy)"),
                ],
                default="agent",
                max_length=20,
            ),
        ),
        migrations.RunPython(remap_legacy_member_roles, noop_reverse),
        migrations.AlterField(
            model_name="organizationmembership",
            name="role",
            field=models.CharField(
                choices=[
                    ("owner", "Owner"),
                    ("manager", "Manager"),
                    ("accountant", "Accountant"),
                    ("insurance_agent", "Insurance Agent"),
                    ("agent", "Agent"),
                ],
                default="agent",
                max_length=20,
            ),
        ),
    ]
