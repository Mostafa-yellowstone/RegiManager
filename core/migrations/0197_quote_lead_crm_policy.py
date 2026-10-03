from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0196_client_external_key"),
    ]

    operations = [
        migrations.AlterField(
            model_name="insurancepolicy",
            name="insurance_company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="policies",
                to="core.insurancecompany",
            ),
        ),
        migrations.AlterField(
            model_name="insurancepolicy",
            name="broker_fee",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=None,
                help_text="Broker fee taken by the agent. Blank until it is entered.",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="insurancepolicy",
            name="commission_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=None,
                help_text="Commission rate in percentage (e.g. 15.00 for 15%). Blank until it is entered.",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="insurancepolicy",
            name="commission_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=None,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="insurancequotelead",
            name="crm_policy",
            field=models.ForeignKey(
                blank=True,
                help_text="CRM policy created from this quote. Reassignment updates that policy's agent.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="quote_leads",
                to="core.insurancepolicy",
            ),
        ),
    ]
