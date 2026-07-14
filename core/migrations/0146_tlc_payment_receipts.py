from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0145_tlc_endorsement_written_premium"),
    ]

    operations = [
        migrations.CreateModel(
            name="TLCPaymentTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("transaction_id", models.CharField(db_index=True, max_length=40, unique=True)),
                (
                    "transaction_type",
                    models.CharField(
                        choices=[
                            ("down_payment", "Down Payment"),
                            ("installment", "Installment Payment"),
                            ("split_payment", "Split Payment"),
                            ("broker_fee", "Broker Fee"),
                            ("dmv", "DMV Payment"),
                            ("reinstatement", "Reinstatement Fee"),
                            ("late_fee", "Late Fee"),
                            ("nsf_fee", "NSF Fee"),
                            ("endorsement", "Endorsement Payment"),
                            ("renewal", "Renewal Payment"),
                            ("additional_premium", "Additional Premium"),
                            ("refund", "Refund"),
                            ("credit", "Credit"),
                            ("balance_adjustment", "Balance Adjustment"),
                            ("other", "Other"),
                        ],
                        default="installment",
                        max_length=30,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("completed", "Completed"),
                            ("pending", "Pending"),
                            ("failed", "Failed"),
                            ("reversed", "Reversed"),
                        ],
                        db_index=True,
                        default="completed",
                        max_length=20,
                    ),
                ),
                ("amount_due", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("amount_received", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("payment_date", models.DateField()),
                ("payment_time", models.TimeField(blank=True, null=True)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "dmv_service",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_transactions",
                        to="core.tlcdmvservice",
                    ),
                ),
                (
                    "endorsement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_transactions",
                        to="core.tlcendorsement",
                    ),
                ),
                (
                    "installment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_transactions",
                        to="core.tlcinstallment",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tlc_payment_transactions",
                        to="core.organization",
                    ),
                ),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payment_transactions",
                        to="core.tlcpolicy",
                    ),
                ),
                (
                    "processed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_payments_processed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reinstatement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_transactions",
                        to="core.tlcreinstatement",
                    ),
                ),
            ],
            options={
                "ordering": ["-payment_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TLCPaymentSplit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "payment_method",
                    models.CharField(
                        choices=[
                            ("cash", "Cash"),
                            ("zelle", "Zelle"),
                            ("checks", "Checks"),
                            ("visa", "Visa"),
                            ("mastercard", "Mastercard"),
                            ("discover", "Discover"),
                            ("american_express", "American Express"),
                            ("credit_card", "Credit Card"),
                            ("debit_card", "Debit Card"),
                            ("money_order", "Money Order"),
                            ("wire", "Wire Transfer"),
                            ("other", "Other"),
                        ],
                        default="cash",
                        max_length=40,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("reference_number", models.CharField(blank=True, default="", max_length=120)),
                ("approval_number", models.CharField(blank=True, default="", max_length=120)),
                ("last_four", models.CharField(blank=True, default="", max_length=8)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "transaction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="splits",
                        to="core.tlcpaymenttransaction",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="TLCReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("receipt_number", models.CharField(db_index=True, max_length=40, unique=True)),
                ("version", models.PositiveSmallIntegerField(default=1)),
                ("generated_at", models.DateTimeField(auto_now_add=True)),
                ("content_hash", models.CharField(blank=True, default="", max_length=64)),
                ("snapshot_json", models.JSONField(blank=True, default=dict)),
                ("pdf_file", models.FileField(blank=True, null=True, upload_to="tlc_receipts/")),
                (
                    "generated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tlc_receipts_generated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="receipts",
                        to="core.tlcpolicy",
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="receipts",
                        to="core.tlcpaymenttransaction",
                    ),
                ),
            ],
            options={
                "ordering": ["-generated_at", "-id"],
                "unique_together": {("transaction", "version")},
            },
        ),
    ]
