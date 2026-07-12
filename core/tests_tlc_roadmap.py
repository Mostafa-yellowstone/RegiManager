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
        self.assertEqual(first.balance, Decimal("508.00"))
