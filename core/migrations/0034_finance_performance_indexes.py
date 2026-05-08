from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0033_organization_is_active_and_membership_is_active"),
    ]

    operations = [
        migrations.AlterField(
            model_name="servicerecord",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AddIndex(
            model_name="servicerecord",
            index=models.Index(fields=["organization", "created_at"], name="core_servic_organiza_d0f87f_idx"),
        ),
        migrations.AddIndex(
            model_name="servicerecord",
            index=models.Index(fields=["organization", "status", "created_at"], name="core_servic_organiza_417c34_idx"),
        ),
    ]
