"""Tests for the TLC Policy Profitability Engine space."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Client, Organization, OrganizationMembership, Space
from core.tlc_models import TLCDMVService, TLCInstallment, TLCPolicy, TLCPremiumBreakdown
from core.tlc_profitability import build_policy_profitability, tlc_dashboard_stats

User = get_user_model()


class TLCSpaceTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="TLC Test PSB", city="Queens", state="NY")
        self.owner = User.objects.create_user(username="tlcowner", password="pass12345")
        self.membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
            can_view_spaces=True,
            can_deal_with_tlc=True,
        )
        self.space = Space.objects.create(
            organization=self.org,
            key="tlc",
            label="TLC",
            description="TLC profitability",
        )
        self.membership.accessible_spaces.add(self.space)
        self.client.login(username="tlcowner", password="pass12345")
        session = self.client.session
        session["active_organization_id"] = self.org.id
        session.save()

    def test_spaces_home_creates_tlc_space_via_provisioning(self):
        from core.owner_api_metrics import ensure_default_spaces

        ensure_default_spaces(self.org)
        self.assertTrue(Space.objects.filter(organization=self.org, key="tlc").exists())

    def test_tlc_space_renders(self):
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TLC Policy Profitability Engine")

    def test_create_policy_and_profitability_snapshot(self):
        policy = TLCPolicy.objects.create(
            organization=self.org,
            space=self.space,
            policy_number="TLC-1001",
            carrier="Maya Assurance",
            named_insured="John Driver",
            status=TLCPolicy.Status.ACTIVE,
            commission_rate=Decimal("12.00"),
            broker_fee_collected=Decimal("350.00"),
            added_by=self.owner,
        )
        TLCPremiumBreakdown.objects.create(
            policy=policy,
            total_written_premium=Decimal("8950.00"),
            down_payment=Decimal("1600.00"),
            monthly_installment=Decimal("740.00"),
            number_of_installments=10,
        )
        policy.save()
        TLCInstallment.objects.create(
            policy=policy,
            installment_number=1,
            due_date="2026-01-10",
            amount=Decimal("740.00"),
            installment_fee=Decimal("5.00"),
            is_paid=True,
            payment_date="2026-01-08",
            balance=Decimal("0.00"),
        )
        TLCDMVService.objects.create(
            policy=policy,
            service_type=TLCDMVService.ServiceType.REGISTRATION,
            fee_charged=Decimal("250.00"),
            dmv_tlc_cost=Decimal("187.50"),
        )

        snapshot = build_policy_profitability(policy)
        self.assertEqual(snapshot["written_premium"], "8950.00")
        self.assertEqual(snapshot["broker_fees_collected"], "350.00")
        self.assertEqual(snapshot["dmv_net_profit"], "62.50")
        self.assertEqual(snapshot["installment_fees_collected"], "5.00")
        self.assertIn("net_profit", snapshot)

        stats = tlc_dashboard_stats(self.space)
        self.assertEqual(stats["total_policies"], 1)
        self.assertEqual(stats["active_policies"], 1)

    def test_add_tlc_policy_via_post(self):
        response = self.client.post(
            reverse("add-tlc-policy", args=[self.space.id]),
            {
                "policy_number": "TLC-2002",
                "carrier": "American Transit",
                "named_insured": "Jane Medallion",
                "total_written_premium": "5000.00",
                "down_payment": "1000.00",
                "commission_rate": "10",
                "status": "active",
            },
        )
        self.assertEqual(response.status_code, 302)
        policy = TLCPolicy.objects.get(policy_number="TLC-2002")
        self.assertEqual(policy.carrier, "American Transit")
        detail = self.client.get(reverse("tlc-policy-detail", args=[self.space.id, policy.id]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "TLC-2002")
        self.assertContains(detail, "+ New Carrier")

    def test_add_tlc_carrier_via_ajax(self):
        response = self.client.post(
            reverse("add-tlc-carrier", args=[self.space.id]),
            {"name": "Maya Assurance"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["name"], "Maya Assurance")
        page = self.client.get(reverse("inventory-detail", args=[self.space.id]) + "?tab=policies")
        self.assertContains(page, "Maya Assurance")
        self.assertContains(page, "+ New Carrier")

    def test_edit_tlc_installment_via_post(self):
        policy = TLCPolicy.objects.create(
            organization=self.org,
            space=self.space,
            policy_number="TLC-EDIT-1",
            carrier="Maya Assurance",
            named_insured="Edit Test",
            status=TLCPolicy.Status.ACTIVE,
            added_by=self.owner,
        )
        installment = TLCInstallment.objects.create(
            policy=policy,
            installment_number=1,
            due_date="2026-02-01",
            amount=Decimal("500.00"),
            installment_fee=Decimal("5.00"),
            is_paid=False,
            balance=Decimal("505.00"),
        )
        response = self.client.post(
            reverse("edit-tlc-installment", args=[installment.id]),
            {
                "installment_number": "1",
                "due_date": "2026-02-15",
                "gross_amount": "555.00",
                "installment_fee": "5.00",
                "late_fee": "0",
                "nsf_fee": "0",
                "balance": "550.00",
            },
        )
        self.assertEqual(response.status_code, 302)
        installment.refresh_from_db()
        self.assertFalse(installment.is_paid)
        self.assertEqual(installment.amount, Decimal("550.00"))
        detail = self.client.get(reverse("tlc-policy-detail", args=[self.space.id, policy.id]))
        self.assertContains(detail, "Collect Payment")
        self.assertContains(detail, "Invoices")
