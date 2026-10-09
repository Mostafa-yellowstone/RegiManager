import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0200_directory_space"),
    ]

    operations = [
        migrations.CreateModel(
            name="DirectoryNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=120)),
                ("body", models.TextField(blank=True, default="")),
                ("position", models.PositiveIntegerField(default=0)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="note_items", to="core.directoryentry")),
            ],
            options={"ordering": ["position", "id"]},
        ),
    ]
