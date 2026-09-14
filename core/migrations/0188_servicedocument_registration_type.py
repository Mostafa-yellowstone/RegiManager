# Generated manually for ServiceDocument.registration type

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0187_client_chat_message"),
    ]

    operations = [
        migrations.AlterField(
            model_name="servicedocument",
            name="document_type",
            field=models.CharField(
                choices=[
                    ("title", "Title"),
                    ("registration", "Registration"),
                    ("bill_of_sale", "Bill of Sale"),
                    ("driver_license", "Driver License"),
                    ("insurance_id", "Insurance ID Card"),
                    ("mv82", "MV82"),
                    ("dtf802", "DTF 802"),
                    ("reassignments", "Reassignments"),
                    ("mv50", "MV50"),
                    ("other", "Other docs"),
                ],
                max_length=30,
            ),
        ),
    ]
