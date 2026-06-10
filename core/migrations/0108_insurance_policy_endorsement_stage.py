from django.db import migrations, models


def merge_endorsement_stages(apps, schema_editor):
    InsurancePolicy = apps.get_model("core", "InsurancePolicy")
    InsurancePolicy.objects.filter(
        stage__in=["endorsement_quote", "endorsement_bound"]
    ).update(stage="endorsement")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0107_insurance_policy_endorsement_stages"),
    ]

    operations = [
        migrations.RunPython(merge_endorsement_stages, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="insurancepolicy",
            name="stage",
            field=models.CharField(
                choices=[
                    ("quote", "Quote"),
                    ("bound", "Bound"),
                    ("endorsement", "Endorsement"),
                ],
                default="quote",
                max_length=20,
            ),
        ),
    ]
