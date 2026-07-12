# Generated manually for TLC Policy Profitability Engine

import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0138_owner_notification_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationmembership",
            name="can_deal_with_tlc",
            field=models.BooleanField(
                default=False,
                help_text="Can this member manage TLC policy profitability records?",
            ),
        ),
        migrations.CreateModel(
            name="TLCPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("policy_number", models.CharField(db_index=True, max_length=100)),
                ("carrier", models.CharField(blank=True, default="", max_length=120)),
                (
                    "policy_type",
                    models.CharField(
                        choices=[
                            ("new_business", "New Business"),
                            ("renewal", "Renewal"),
                            ("rewrite", "Rewrite"),
                        ],
                        default="new_business",
                        max_length=20,
                    ),
                ),
                ("named_insured", models.CharField(blank=True, default="", max_length=200)),
                ("business_name", models.CharField(blank=True, default="", max_length=200)),
                ("tlc_base_number", models.CharField(blank=True, default="", max_length=40)),
                ("tlc_license_number", models.CharField(blank=True, default="", max_length=40)),
                ("vin", models.CharField(blank=True, default="", max_length=17)),
                ("plate_number", models.CharField(blank=True, default="", max_length=20)),
                ("driver_name", models.CharField(blank=True, default="", max_length=200)),
                ("broker_name", models.CharField(blank=True, default="", max_length=120)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("pending", "Pending"),
                            ("cancelled", "Cancelled"),
                            ("suspended", "Suspended"),
                            ("reinstated", "Reinstated"),
                            ("expired", "Expired"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("expiration_date", models.DateField(blank=True, null=True)),
                ("renewal_date", models.DateField(blank=True, null=True)),
                (
                    "commission_rate",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Carrier commission rate as a percentage.",
                        max_digits=5,
                    ),
                ),
                (
                    "carrier_commission_amount",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "renewal_commission_rate",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5),
                ),
                (
                    "producer_commission_amount",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "csr_commission_amount",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "broker_fee_collected",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "finance_fee_collected",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "amount_collected_from_client",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Total premium/fees collected from the customer (excluding DMV).",
                        max_digits=12,
                    ),
                ),
                (
                    "amount_remitted_to_carrier",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "carrier_credits",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "carrier_refunds",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "commission_received",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "commission_chargeback",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "endorsement_balance",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "added_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="added_tlc_policies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "client",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_policies",
                        to="core.client",
                    ),
                ),
                (
                    "csr",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_csr_policies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "insurance_policy",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional link to the general insurance CRM policy.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_policies",
                        to="core.insurancepolicy",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tlc_policies",
                        to="core.organization",
                    ),
                ),
                (
                    "producer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_produced_policies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "space",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tlc_policies",
                        to="core.space",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_policies",
                        to="core.vehicle",
                    ),
                ),
            ],
            options={
                "verbose_name": "TLC policy",
                "verbose_name_plural": "TLC policies",
                "ordering": ["-created_at"],
                "unique_together": {("organization", "policy_number")},
            },
        ),
        migrations.CreateModel(
            name="TLCPremiumBreakdown",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "total_written_premium",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                ("down_payment", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("amount_financed", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("number_of_installments", models.PositiveSmallIntegerField(default=0)),
                (
                    "monthly_installment",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                ("policy_fee", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("installment_fee", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("finance_charge", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("taxes", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("mvr_fee", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("inspection_fee", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("sr22_fee", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                (
                    "additional_driver_fee",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "additional_vehicle_fee",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "endorsement_charges",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                ("cancellation_fee", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                (
                    "reinstatement_fee",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "returned_check_fee",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                ("late_payment_fee", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                (
                    "other_carrier_fees",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "policy",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="premium_breakdown",
                        to="core.tlcpolicy",
                    ),
                ),
            ],
            options={
                "verbose_name": "TLC premium breakdown",
                "verbose_name_plural": "TLC premium breakdowns",
            },
        ),
        migrations.CreateModel(
            name="TLCInstallment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("installment_number", models.PositiveSmallIntegerField()),
                ("due_date", models.DateField()),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("is_paid", models.BooleanField(default=False)),
                ("payment_date", models.DateField(blank=True, null=True)),
                ("late_fee", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("nsf_fee", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("was_reinstated", models.BooleanField(default=False)),
                ("balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="installments",
                        to="core.tlcpolicy",
                    ),
                ),
            ],
            options={
                "ordering": ["installment_number"],
                "unique_together": {("policy", "installment_number")},
            },
        ),
        migrations.CreateModel(
            name="TLCReinstatement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cancellation_date", models.DateField(blank=True, null=True)),
                ("cancellation_reason", models.CharField(blank=True, default="", max_length=255)),
                ("reinstatement_date", models.DateField(blank=True, null=True)),
                (
                    "reinstatement_fee",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                ("carrier_confirmation", models.CharField(blank=True, default="", max_length=120)),
                ("is_paid", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reinstatements",
                        to="core.tlcpolicy",
                    ),
                ),
                (
                    "processed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_reinstatements_processed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-reinstatement_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TLCEndorsement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "endorsement_type",
                    models.CharField(
                        choices=[
                            ("added_driver", "Added Driver"),
                            ("removed_driver", "Removed Driver"),
                            ("address_change", "Address Change"),
                            ("vehicle_change", "Vehicle Change"),
                            ("coverage_change", "Coverage Change"),
                            ("plate_change", "Plate Change"),
                            ("tlc_number_change", "TLC Number Change"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=30,
                    ),
                ),
                (
                    "premium_difference",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                (
                    "commission_difference",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
                ),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="endorsements",
                        to="core.tlcpolicy",
                    ),
                ),
                (
                    "processed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_endorsements_processed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-effective_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TLCDMVService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "service_type",
                    models.CharField(
                        choices=[
                            ("registration", "Registration"),
                            ("plate_transfer", "Plate Transfer"),
                            ("title", "Title"),
                            ("duplicate_registration", "Duplicate Registration"),
                            ("inspection", "Inspection"),
                            ("tlc_filing", "TLC Filing"),
                            ("other", "Other"),
                        ],
                        default="registration",
                        max_length=30,
                    ),
                ),
                ("fee_charged", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("dmv_tlc_cost", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("agency_profit", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("service_date", models.DateField(blank=True, null=True)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dmv_services",
                        to="core.tlcpolicy",
                    ),
                ),
            ],
            options={
                "ordering": ["-service_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TLCAgencyExpense",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "expense_type",
                    models.CharField(
                        choices=[
                            ("producer_commission", "Producer Commission"),
                            ("csr_bonus", "CSR Bonus"),
                            ("merchant_fees", "Merchant Fees"),
                            ("processing_fees", "Processing Fees"),
                            ("chargebacks", "Chargebacks"),
                            ("advertising", "Advertising Cost"),
                            ("office_allocation", "Office Allocation"),
                            ("software", "Software Cost"),
                            ("payroll", "Payroll Allocation"),
                            ("misc", "Misc Expenses"),
                        ],
                        default="misc",
                        max_length=30,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("expense_date", models.DateField(blank=True, null=True)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agency_expenses",
                        to="core.tlcpolicy",
                    ),
                ),
            ],
            options={
                "ordering": ["-expense_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TLCCarrierRemittance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("remittance_date", models.DateField(blank=True, null=True)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="carrier_remittances",
                        to="core.tlcpolicy",
                    ),
                ),
            ],
            options={
                "ordering": ["-remittance_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TLCPolicyDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "document_type",
                    models.CharField(
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
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=30,
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("file", models.FileField(blank=True, null=True, upload_to="tlc_policy_documents/")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="core.tlcpolicy",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_documents_uploaded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-uploaded_at"],
            },
        ),
        migrations.CreateModel(
            name="TLCPolicyTimelineEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("quote", "Quote"),
                            ("bound", "Bound"),
                            ("down_payment", "Down Payment"),
                            ("issued", "Issued"),
                            ("installment", "Installment"),
                            ("cancellation", "Cancellation"),
                            ("reinstatement", "Reinstatement"),
                            ("endorsement", "Endorsement"),
                            ("renewal", "Renewal"),
                            ("expired", "Expired"),
                        ],
                        max_length=20,
                    ),
                ),
                ("event_date", models.DateField(blank=True, null=True)),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_timeline_events_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="timeline_events",
                        to="core.tlcpolicy",
                    ),
                ),
            ],
            options={
                "ordering": ["event_date", "created_at"],
            },
        ),
    ]
