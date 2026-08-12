from django.db import migrations, models


def forwards_merge_new_into_assigned(apps, schema_editor):
    Lead = apps.get_model("core", "InsuranceQuoteLead")
    Lead.objects.filter(stage="new").update(stage="assigned")


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0169_quote_lead_additional_vehicles"),
    ]

    operations = [
        migrations.AlterField(
            model_name="insurancequotelead",
            name="stage",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("assigned", "Assigned"),
                    ("quoting", "Quoting"),
                    ("quoted", "Quoted"),
                    ("won", "Won"),
                    ("lost", "Lost"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="assigned",
                max_length=20,
            ),
        ),
        migrations.RunPython(forwards_merge_new_into_assigned, backwards_noop),
    ]
