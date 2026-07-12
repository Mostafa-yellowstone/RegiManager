# TLC roadmap: installment fees, commission rules, finance, reminders, reconciliation

import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0139_tlc_space"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="tlcinstallment",
            name="installment_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Per-installment carrier/installment fee charged to the customer.",
                max_digits=12,
            ),
        ),
        migrations.CreateModel(
            name="TLCCarrierCommissionRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("carrier", models.CharField(db_index=True, max_length=120)),
                ("policy_type", models.CharField(blank=True, choices=[("new_business", "New Business"), ("renewal", "Renewal"), ("rewrite", "Rewrite")], default="", help_text="Leave blank to apply to all policy types for this carrier.", max_length=20)),
                ("product_type", models.CharField(blank=True, default="", help_text="Optional product label, e.g. TLC Liability, Commercial Auto.", max_length=60)),
                ("commission_rate", models.DecimalField(decimal_places=2, max_digits=5)),
                ("renewal_commission_rate", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5)),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tlc_commission_rules", to="core.organization")),
            ],
            options={"ordering": ["carrier", "policy_type", "product_type"], "unique_together": {("organization", "carrier", "policy_type", "product_type")}},
        ),
        migrations.CreateModel(
            name="TLCFinanceCompany",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("contact_phone", models.CharField(blank=True, default="", max_length=40)),
                ("contact_email", models.EmailField(blank=True, default="", max_length=254)),
                ("default_installment_fee", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tlc_finance_companies", to="core.organization")),
            ],
            options={"ordering": ["name"], "unique_together": {("organization", "name")}},
        ),
        migrations.CreateModel(
            name="TLCCarrierStatement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("carrier", models.CharField(db_index=True, max_length=120)),
                ("statement_date", models.DateField()),
                ("period_start", models.DateField(blank=True, null=True)),
                ("period_end", models.DateField(blank=True, null=True)),
                ("total_premium", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("total_commission", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("total_remitted", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("is_reconciled", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tlc_carrier_statements", to="core.organization")),
            ],
            options={"ordering": ["-statement_date", "-created_at"]},
        ),
        migrations.CreateModel(
            name="TLCPolicyFinance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("contract_number", models.CharField(blank=True, default="", max_length=80)),
                ("amount_financed", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("payoff_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("next_payoff_date", models.DateField(blank=True, null=True)),
                ("is_delinquent", models.BooleanField(default=False)),
                ("delinquency_notes", models.TextField(blank=True, default="")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("finance_company", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="policies", to="core.tlcfinancecompany")),
                ("policy", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="finance_contract", to="core.tlcpolicy")),
            ],
        ),
        migrations.CreateModel(
            name="TLCInstallmentReminder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(choices=[("email", "Email"), ("sms", "SMS")], default="email", max_length=10)),
                ("days_before_due", models.PositiveSmallIntegerField(default=3, help_text="0 = remind on due date.")),
                ("scheduled_for", models.DateTimeField(db_index=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed"), ("cancelled", "Cancelled")], db_index=True, default="pending", max_length=12)),
                ("recipient_email", models.EmailField(blank=True, default="", max_length=254)),
                ("recipient_phone", models.CharField(blank=True, default="", max_length=20)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("installment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="reminders", to="core.tlcinstallment")),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="installment_reminders", to="core.tlcpolicy")),
            ],
            options={"ordering": ["scheduled_for"]},
        ),
        migrations.CreateModel(
            name="TLCCarrierStatementLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("policy_number", models.CharField(db_index=True, max_length=100)),
                ("premium_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("commission_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("remitted_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("is_matched", models.BooleanField(default=False)),
                ("variance_notes", models.CharField(blank=True, default="", max_length=255)),
                ("policy", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="carrier_statement_lines", to="core.tlcpolicy")),
                ("statement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="core.tlccarrierstatement")),
            ],
            options={"ordering": ["policy_number"]},
        ),
    ]
