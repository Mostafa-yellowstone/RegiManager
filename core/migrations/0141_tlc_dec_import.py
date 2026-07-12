# TLC declaration page import: insured metadata, vehicles, drivers

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0140_tlc_roadmap"),
    ]

    operations = [
        migrations.AddField(
            model_name="tlcpolicy",
            name="form_of_business",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="tlcpolicy",
            name="insured_address",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="tlcpolicy",
            name="issue_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="tlcpolicydocument",
            name="document_type",
            field=models.CharField(
                choices=[
                    ("driver_license", "Driver License"),
                    ("tlc_license", "TLC License"),
                    ("registration", "Registration"),
                    ("coi", "Certificate of Insurance"),
                    ("id_cards", "ID Cards"),
                    ("payment_receipt", "Payment Receipt"),
                    ("finance_agreement", "Finance Agreement"),
                    ("carrier_notice", "Carrier Notice"),
                    ("cancellation_notice", "Cancellation Notice"),
                    ("reinstatement_notice", "Reinstatement Notice"),
                    ("dmv_document", "DMV Document"),
                    ("photo", "Photo"),
                    ("signed_application", "Signed Application"),
                    ("declaration_page", "Declaration Page"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=30,
            ),
        ),
        migrations.CreateModel(
            name="TLCPolicyDriver",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("expiry_date", models.DateField(blank=True, null=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="policy_drivers",
                        to="core.tlcpolicy",
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="TLCPolicyVehicle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("auto_number", models.PositiveSmallIntegerField(default=1)),
                ("year", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("make", models.CharField(blank=True, default="", max_length=60)),
                ("vin", models.CharField(blank=True, default="", max_length=17)),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("expiration_date", models.DateField(blank=True, null=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="policy_vehicles",
                        to="core.tlcpolicy",
                    ),
                ),
            ],
            options={
                "ordering": ["auto_number"],
                "unique_together": {("policy", "auto_number")},
            },
        ),
    ]
