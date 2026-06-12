import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0116_clientintake_insurance_id_card"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientintake",
            name="intake_note",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="clientintake",
            name="partner_address",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="clientintake",
            name="partner_email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name="clientintake",
            name="partner_name",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="clientintake",
            name="partner_phone",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="clientintake",
            name="selected_referral",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="intakes",
                to="core.referral",
            ),
        ),
    ]
