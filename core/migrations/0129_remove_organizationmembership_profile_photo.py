from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0128_membership_profile_photo_finance_perms"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="organizationmembership",
            name="profile_photo",
        ),
    ]
