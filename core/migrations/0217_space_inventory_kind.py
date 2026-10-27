from django.db import migrations, models


def mark_custom_inventory(apps, schema_editor):
    Space = apps.get_model("core", "Space")
    Space.objects.filter(key="custom_inventory").update(kind="inventory")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0216_carrier_quote_lines"),
    ]

    operations = [
        migrations.AddField(
            model_name="space",
            name="kind",
            field=models.CharField(
                blank=True,
                default="",
                help_text="inventory uses the shared stock, sales, and invoice desk. Blank keeps the space's own page.",
                max_length=20,
            ),
        ),
        migrations.RunPython(mark_custom_inventory, migrations.RunPython.noop),
    ]
