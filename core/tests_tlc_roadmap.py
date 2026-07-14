"""Additional tests for TLC roadmap features."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Organization, OrganizationMembership, Space
from core.tlc_commissions import apply_commission_rule_to_policy
from core.tlc_models import TLCCarrierCommissionRule, TLCPolicy, TLCPremiumBreakdown
from core.tlc_schedule import generate_installment_schedule

User = get_user_model()


class TLCRoadmapTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Roadmap PSB", city="Brooklyn", state="NY")
        self.space = Space.objects.create(organization=self.org, key="tlc", label="TLC")
        self.policy = TLCPolicy.objects.create(
            organization=self.org,
            space=self.space,
            policy_number="TLC-R1",
            carrier="Maya Assurance",
            policy_type=TLCPolicy.PolicyType.NEW_BUSINESS,
        )
        TLCPremiumBreakdown.objects.create(
            policy=self.policy,
            total_written_premium=Decimal("6000.00"),
            monthly_installment=Decimal("500.00"),
            number_of_installments=10,
            installment_fee=Decimal("8.00"),
        )

    def test_commission_rule_auto_applies(self):
        TLCCarrierCommissionRule.objects.create(
            organization=self.org,
            carrier="Maya Assurance",
            policy_type="",
            product_type="",
            commission_rate=Decimal("12.00"),
        )
        self.assertTrue(apply_commission_rule_to_policy(self.policy))
        self.assertEqual(self.policy.commission_rate, Decimal("12.00"))
        self.assertEqual(self.policy.carrier_commission_amount, Decimal("720.00"))

    def test_generate_installment_schedule_includes_fees(self):
        created = generate_installment_schedule(self.policy, replace_existing=True)
        self.assertEqual(created, 10)
        first = self.policy.installments.order_by("installment_number").first()
        self.assertEqual(first.installment_fee, Decimal("8.00"))
        self.assertEqual(first.amount, Decimal("492.00"))
        self.assertEqual(first.balance, Decimal("500.00"))

    def test_generate_installment_schedule_deposit_unnumbered(self):
        breakdown = self.policy.premium_breakdown
        breakdown.down_payment = Decimal("1000.00")
        breakdown.save(update_fields=["down_payment"])
        created = generate_installment_schedule(self.policy, replace_existing=True)
        self.assertEqual(created, 11)
        deposit = self.policy.installments.get(installment_number=0)
        self.assertTrue(deposit.is_deposit)
        self.assertEqual(deposit.display_number, "—")
        self.assertEqual(deposit.notes, "Down Payment")
        first_bill = self.policy.installments.get(installment_number=1)
        self.assertFalse(first_bill.is_deposit)
        self.assertEqual(first_bill.notes, "Bill #1")

    def test_normalize_legacy_deposit_numbering_and_commission(self):
        from core.tlc_installments import annotate_installment_display_numbers
        from core.tlc_models import TLCInstallment
        from core.tlc_schedule import normalize_policy_installment_numbers

        self.policy.commission_rate = Decimal("10.00")
        self.policy.save(update_fields=["commission_rate"])
        TLCInstallment.objects.create(
            policy=self.policy,
            installment_number=1,
            due_date="2026-01-01",
            amount=Decimal("1000.00"),
            installment_fee=Decimal("0.00"),
            commission_amount=Decimal("0.00"),
            notes="DEPOSIT",
        )
        for n in range(2, 11):
            TLCInstallment.objects.create(
                policy=self.policy,
                installment_number=n,
                due_date=f"2026-{n:02d}-01" if n <= 12 else "2026-12-01",
                amount=Decimal("500.00"),
                installment_fee=Decimal("5.00"),
                commission_amount=Decimal("0.00"),
                notes=f"BILL # {n - 1}",
            )
        self.assertTrue(normalize_policy_installment_numbers(self.policy))
        from core.tlc_installments import sync_installment_commissions

        sync_installment_commissions(self.policy)
        deposit = self.policy.installments.get(notes="DEPOSIT")
        bills = list(self.policy.installments.exclude(notes="DEPOSIT").order_by("installment_number"))
        self.assertEqual(deposit.installment_number, 0)
        self.assertEqual([b.installment_number for b in bills], list(range(1, 10)))
        self.assertEqual(bills[0].commission_amount, Decimal("50.00"))
        annotated = annotate_installment_display_numbers(
            list(self.policy.installments.order_by("installment_number"))
        )
        self.assertEqual([row.display_number for row in annotated], ["—"] + [str(i) for i in range(1, 10)])
