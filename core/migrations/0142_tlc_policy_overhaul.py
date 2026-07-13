# TLC policy UX overhaul: cancellations, installment commission, endorsements, remove expenses

import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0141_tlc_dec_import"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="tlcinstallment",
            name="commission_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Agency commission earned on this installment's net premium.",
                max_digits=12,
            ),
        ),
        migrations.RenameField(
            model_name="tlcreinstatement",
            old_name="carrier_confirmation",
            new_name="dmv_document_number",
        ),
        migrations.RemoveField(
            model_name="tlcreinstatement",
            name="is_paid",
        ),
        migrations.RenameField(
            model_name="tlcendorsement",
            old_name="effective_date",
            new_name="coverage_change_date",
        ),
        migrations.AlterField(
            model_name="tlcendorsement",
            name="endorsement_type",
            field=models.CharField(
                choices=[
                    ("added_driver", "Added Driver"),
                    ("removed_driver", "Removed Driver"),
                    ("address_change", "Address Change"),
                    ("add_vehicle", "Add a Vehicle"),
                    ("remove_vehicle", "Remove a Vehicle"),
                    ("replace_vehicle", "Replace a Vehicle"),
                    ("ddc", "DDC"),
                    ("coverage_change", "Coverage Change"),
                    ("plate_change", "Plate Change"),
                    ("tlc_number_change", "TLC Number Change"),
                    ("vehicle_change", "Vehicle Change"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=30,
            ),
        ),
        migrations.CreateModel(
            name="TLCPolicyCancellation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cancellation_date", models.DateField()),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("surrender_plates", "Surrender Plates"),
                            ("moved_carrier", "Moved to Another Carrier"),
                            ("moved_broker", "Moved to Another Broker"),
                            ("custom", "Custom Note"),
                        ],
                        max_length=30,
                    ),
                ),
                ("custom_note", models.TextField(blank=True, default="")),
                ("successor_carrier", models.CharField(blank=True, default="", max_length=120)),
                ("successor_broker", models.CharField(blank=True, default="", max_length=120)),
                ("successor_policy_number", models.CharField(blank=True, default="", max_length=100)),
                ("successor_effective_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cancellations",
                        to="core.tlcpolicy",
                    ),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_cancellations_recorded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-cancellation_date", "-created_at"]},
        ),
        migrations.DeleteModel(
            name="TLCAgencyExpense",
        ),
    ]
