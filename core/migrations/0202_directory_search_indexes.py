from django.db import migrations, models


def create_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    entry = schema_editor.quote_name("core_directoryentry")
    phone = schema_editor.quote_name("core_directoryphone")
    statements = [
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        f"CREATE INDEX IF NOT EXISTS dir_ent_name_trgm ON {entry} USING gin (name gin_trgm_ops)",
        f"CREATE INDEX IF NOT EXISTS dir_ent_email_trgm ON {entry} USING gin (email gin_trgm_ops)",
        f"CREATE INDEX IF NOT EXISTS dir_phone_num_trgm ON {phone} USING gin (number gin_trgm_ops)",
    ]
    for statement in statements:
        schema_editor.execute(statement)


def drop_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name in ("dir_ent_name_trgm", "dir_ent_email_trgm", "dir_phone_num_trgm"):
        schema_editor.execute(f"DROP INDEX IF EXISTS {schema_editor.quote_name(name)}")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0201_directory_notes"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="directoryentry",
            index=models.Index(fields=["space", "name"], name="dir_ent_space_name"),
        ),
        migrations.AddIndex(
            model_name="directoryphone",
            index=models.Index(fields=["entry", "number"], name="dir_phone_entry_num"),
        ),
        migrations.RunPython(create_trigram_indexes, drop_trigram_indexes),
    ]
