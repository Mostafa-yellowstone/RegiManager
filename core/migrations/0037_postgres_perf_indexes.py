from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0036_client_notes_and_notifications"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="client",
            index=models.Index(fields=["organization", "-created_at"], name="core_client_organiz_6b5bc4_idx"),
        ),
        migrations.AddIndex(
            model_name="client",
            index=models.Index(fields=["organization", "last_name", "first_name"], name="core_client_organiz_57b6a8_idx"),
        ),
        migrations.AddIndex(
            model_name="serviceauditlog",
            index=models.Index(fields=["organization", "-created_at"], name="core_servicea_organiz_7afc77_idx"),
        ),
        migrations.AddIndex(
            model_name="serviceauditlog",
            index=models.Index(fields=["service_record", "-created_at"], name="core_servicea_service_3f8ae2_idx"),
        ),
    ]

