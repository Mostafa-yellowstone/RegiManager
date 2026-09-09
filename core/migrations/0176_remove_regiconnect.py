# Generated manually — remove RegiConnect permission flags and drop its tables.

from django.db import migrations, models


REGICONNECT_TABLES = (
    "regiconnect_certificationtestresult",
    "regiconnect_certificationrun",
    "regiconnect_reconciliationexception",
    "regiconnect_acordmapping",
    "regiconnect_sftpfilejob",
    "regiconnect_sftpendpoint",
    "regiconnect_documentexchange",
    "regiconnect_inboundtransaction",
    "regiconnect_webhookevent",
    "regiconnect_policyconnectivity",
    "regiconnect_quoteleadconnectivity",
    "regiconnect_bindtransaction",
    "regiconnect_ratingerror",
    "regiconnect_ratingextension",
    "regiconnect_ratingjob",
    "regiconnect_ratingrequest",
    "regiconnect_canonicalquote",
    "regiconnect_submissionextension",
    "regiconnect_submission",
    "regiconnect_deadletteritem",
    "regiconnect_connectorjob",
    "regiconnect_outboxevent",
    "regiconnect_idempotencyrecord",
    "regiconnect_connectauditevent",
    "regiconnect_secretreference",
    "regiconnect_connection",
    "regiconnect_connector",
    "regiconnect_appetiterule",
    "regiconnect_producercode",
    "regiconnect_appointment",
    "regiconnect_marketprofile",
)


def drop_regiconnect_schema(apps, schema_editor):
    """Drop leftover RegiConnect tables and clear django_migrations rows."""
    connection = schema_editor.connection
    existing = set(connection.introspection.table_names())
    quote = connection.ops.quote_name

    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            for table in REGICONNECT_TABLES:
                if table in existing:
                    cursor.execute(f"DROP TABLE IF EXISTS {quote(table)} CASCADE")
        else:
            if connection.vendor == "sqlite":
                cursor.execute("PRAGMA foreign_keys=OFF")
            for table in REGICONNECT_TABLES:
                if table in existing:
                    cursor.execute(f"DROP TABLE IF EXISTS {quote(table)}")
            if connection.vendor == "sqlite":
                cursor.execute("PRAGMA foreign_keys=ON")

        if "django_migrations" in existing or "django_migrations" in set(
            connection.introspection.table_names()
        ):
            cursor.execute("DELETE FROM django_migrations WHERE app = %s", ["regiconnect"])


def noop_reverse(apps, schema_editor):
    """RegiConnect removal is irreversible."""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0175_referral_document"),
    ]

    operations = [
        migrations.RunPython(drop_regiconnect_schema, noop_reverse),
        migrations.RemoveField(
            model_name="organizationmembership",
            name="can_manage_regiconnect",
        ),
        migrations.RemoveField(
            model_name="organizationmembership",
            name="can_view_regiconnect",
        ),
    ]
