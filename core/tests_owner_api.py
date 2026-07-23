"""Tests for owner companion API."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from core.models import (
    Client,
    DailyPaymentTransaction,
    InsuranceCompany,
    InsurancePolicy,
    MotorclubMembership,
    Notification,
    Organization,
    OrganizationMembership,
    ServiceRecord,
    Space,
)
from core.owner_api_metrics import build_system_profit_summary

User = get_user_model()


class OwnerAPITests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Owner PSB", city="Albany", state="NY")
        self.owner = User.objects.create_user(username="owner1", password="pass12345")
        self.agent = User.objects.create_user(username="agent1", password="pass12345")
        self.owner_mem = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
            can_view_spaces=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.agent,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )
        self.insurance_space = Space.objects.create(
            organization=self.org,
            key="insurance",
            label="Insurance",
        )
        self.owner_mem.accessible_spaces.add(self.insurance_space)
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
        )
        self.company = InsuranceCompany.objects.create(
            organization=self.org,
            name="Test Insurance Co",
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.agent,
            client_name="Jane Doe",
            service_type="registration",
            status="completed",
            service_fee=Decimal("100.00"),
            processing_fee=Decimal("25.00"),
            transaction_date=date.today(),
        )
        self.owner_token = Token.objects.create(user=self.owner)
        self.agent_token = Token.objects.create(user=self.agent)

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_owner_overview_returns_profit_data(self):
        self._auth(self.owner_token)
        response = self.client.get(reverse("api-owner-overview"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("profit", response.data)
        self.assertIn("combined_profit", response.data["profit"])
        self.assertEqual(response.data["profit"]["dmv_core"]["today"]["total_records"], 1)

    def test_agent_without_finance_permission_denied(self):
        self._auth(self.agent_token)
        response = self.client.get(reverse("api-owner-overview"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_finance_compare_requires_months(self):
        self._auth(self.owner_token)
        response = self.client.get(reverse("api-owner-finance-compare"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_finance_compare_returns_deltas(self):
        self._auth(self.owner_token)
        response = self.client.get(
            reverse("api-owner-finance-compare"),
            {"compare_a": "2026-04", "compare_b": "2026-05"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("deltas", response.data)

    def test_policy_bound_notifies_owner(self):
        policy = InsurancePolicy.objects.create(
            organization=self.org,
            client=self.client_obj,
            policy_number="POL-100",
            insurance_company=self.company,
            premium=Decimal("1200.00"),
            commission_rate=Decimal("10.00"),
            start_date=date.today(),
            end_date=date.today().replace(month=12, day=31),
            stage="quote",
            status="pending",
            bound_date=date.today(),
            added_by=self.agent,
        )
        policy.stage = "bound"
        policy.status = "active"
        policy.save()

        self.assertTrue(
            Notification.objects.filter(
                user=self.owner,
                event_type="policy_bound",
                policy=policy,
            ).exists()
        )

    def test_notifications_list_filters_policy_bound(self):
        Notification.objects.create(
            user=self.owner,
            client=self.client_obj,
            organization=self.org,
            event_type="policy_bound",
            title="Policy bound",
            message="Test",
        )
        self._auth(self.owner_token)
        response = self.client.get(
            reverse("api-owner-notifications"),
            {"event_type": "policy_bound"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["notifications"]), 1)

    def test_owner_spaces_list(self):
        self._auth(self.owner_token)
        response = self.client.get(reverse("api-owner-spaces"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["spaces"]), 1)

    def test_finance_summary_nests_daily_payments_by_domain(self):
        DailyPaymentTransaction.objects.create(
            organization=self.org,
            client=self.client_obj,
            transaction_date=date.today(),
            amount=Decimal("40.00"),
            payment_type="new_business",
            payment_method="cash",
            recorded_by=self.agent,
        )
        ServiceRecord.objects.filter(organization=self.org).update(
            payment_method="cash",
            paid_amount=Decimal("100.00"),
            service_fee=Decimal("100.00"),
        )
        self._auth(self.owner_token)
        response = self.client.get(reverse("api-owner-finance-summary"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("daily_payments", response.data)
        self.assertIn("daily_payments", response.data["dmv"])
        self.assertIn("daily_payments", response.data["insurance"])
        self.assertEqual(
            response.data["insurance"]["daily_payments"]["grand_total"],
            "40.00",
        )
        # DMV intake must not include the insurance daily payment.
        self.assertEqual(
            response.data["dmv"]["daily_payments"]["grand_total"],
            "100.00",
        )

    def test_combined_profit_does_not_double_count_insurance(self):
        InsurancePolicy.objects.create(
            organization=self.org,
            client=self.client_obj,
            policy_number="POL-COMB",
            insurance_company=self.company,
            premium=Decimal("1000.00"),
            commission_rate=Decimal("10.00"),
            broker_fee=Decimal("50.00"),
            start_date=date.today(),
            end_date=date.today().replace(month=12, day=31),
            stage="bound",
            status="active",
            bound_date=date.today(),
            added_by=self.agent,
        )
        summary = build_system_profit_summary(
            self.org,
            self.owner_mem,
            ServiceRecord.objects.filter(organization=self.org),
            date.today(),
        )
        dmv_today = Decimal(summary["dmv_core"]["today"]["gross_profit"])
        spaces_today = sum(
            (Decimal(s["today"]["profit"]) for s in summary["spaces"]),
            Decimal("0"),
        )
        expected = dmv_today + spaces_today
        self.assertEqual(Decimal(summary["combined_profit"]["today"]), expected)
        # Insurance detail exists but must not be added again on top of spaces.
        self.assertEqual(
            Decimal(summary["insurance"]["today"]["total_profit"]),
            Decimal("150.00"),
        )
        self.assertNotEqual(
            Decimal(summary["combined_profit"]["today"]),
            expected + Decimal(summary["insurance"]["today"]["total_profit"]),
        )

    def test_overview_custom_range_returns_ledger_totals(self):
        in_range = date(2026, 7, 10)
        out_of_range = date(2026, 7, 1)
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.agent,
            client_name="In Range",
            service_type="registration",
            status="completed",
            service_fee=Decimal("200.00"),
            processing_fee=Decimal("50.00"),
            payment_method="cash",
            paid_amount=Decimal("50.00"),
            transaction_date=in_range,
            receipt_number="RCPT-RANGE-IN-1",
            case_id="CASE-RANGE-IN-1",
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.agent,
            client_name="Out of Range",
            service_type="registration",
            status="completed",
            service_fee=Decimal("999.00"),
            processing_fee=Decimal("999.00"),
            payment_method="zelle",
            paid_amount=Decimal("999.00"),
            transaction_date=out_of_range,
            receipt_number="RCPT-RANGE-OUT-1",
            case_id="CASE-RANGE-OUT-1",
        )
        self._auth(self.owner_token)
        response = self.client.get(
            reverse("api-owner-overview"),
            {"from_date": "2026-07-10", "to_date": "2026-07-12"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        custom = response.data["profit"]["dmv_core"]["custom"]
        self.assertEqual(custom["total_records"], 1)
        # service_fee is recomputed from processing_fee on save
        self.assertEqual(custom["gross_profit"], "50.00")
        self.assertEqual(custom["total_revenue"], "50.00")
        self.assertEqual(response.data["range"]["source"], "ledger")
        self.assertEqual(
            response.data["profit"]["combined_profit"]["custom"],
            custom["gross_profit"],
        )

    def test_finance_summary_custom_range_payment_cards(self):
        ServiceRecord.objects.filter(organization=self.org).delete()
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.agent,
            client_name="Range Cash",
            service_type="registration",
            status="completed",
            service_fee=Decimal("80.00"),
            processing_fee=Decimal("20.00"),
            payment_method="cash",
            paid_amount=Decimal("20.00"),
            transaction_date=date(2026, 7, 11),
            receipt_number="RCPT-RANGE-CASH-1",
            case_id="CASE-RANGE-CASH-1",
        )
        DailyPaymentTransaction.objects.create(
            organization=self.org,
            client=self.client_obj,
            transaction_date=date(2026, 7, 11),
            amount=Decimal("35.00"),
            payment_type="new_business",
            payment_method="zelle",
            recorded_by=self.agent,
        )
        self._auth(self.owner_token)
        response = self.client.get(
            reverse("api-owner-finance-summary"),
            {"from_date": "2026-07-11", "to_date": "2026-07-11"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["dmv"]["custom"]["gross_profit"], "20.00")
        self.assertEqual(response.data["dmv"]["custom"]["total_revenue"], "20.00")
        self.assertEqual(response.data["dmv"]["daily_payments"]["grand_total"], "20.00")
        self.assertEqual(response.data["insurance"]["daily_payments"]["grand_total"], "35.00")

    def test_invalid_date_range_returns_400(self):
        self._auth(self.owner_token)
        response = self.client.get(
            reverse("api-owner-overview"),
            {"from_date": "2026-07-20", "to_date": "2026-07-10"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_finance_records_endpoint(self):
        ServiceRecord.objects.filter(organization=self.org).update(
            payment_method="cash",
            paid_amount=Decimal("100.00"),
            service_fee=Decimal("100.00"),
        )
        self._auth(self.owner_token)
        response = self.client.get(
            reverse("api-owner-finance-records"),
            {
                "category": "dmv",
                "method": "cash",
                "from_date": date.today().isoformat(),
                "to_date": date.today().isoformat(),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["method"], "cash")

    def test_finance_records_forbidden_for_agent(self):
        self._auth(self.agent_token)
        response = self.client.get(reverse("api-owner-finance-records"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_motorclub_space_detail_and_memberships(self):
        mc_space = Space.objects.create(
            organization=self.org,
            key="motorclub",
            label="Motor Club",
            description="Roadside assistance",
        )
        self.owner_mem.accessible_spaces.add(mc_space)
        MotorclubMembership.objects.create(
            organization=self.org,
            space=mc_space,
            client=self.client_obj,
            channel=MotorclubMembership.ChannelChoices.DIRECT,
            tier=50,
            status=MotorclubMembership.StatusChoices.ACTIVE,
            start_date=date.today(),
            provider_profit=Decimal("20.00"),
            psb_profit=Decimal("30.00"),
            added_by=self.agent,
        )
        MotorclubMembership.objects.create(
            organization=self.org,
            space=mc_space,
            client=self.client_obj,
            channel=MotorclubMembership.ChannelChoices.B2B,
            tier=75,
            status=MotorclubMembership.StatusChoices.PENDING,
            start_date=date.today(),
            provider_profit=Decimal("25.00"),
            psb_profit=Decimal("50.00"),
            added_by=self.agent,
        )

        self._auth(self.owner_token)
        detail = self.client.get(reverse("api-owner-space-detail", args=[mc_space.id]))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["key"], "motorclub")
        self.assertIn("motorclub_summary", detail.data)
        self.assertEqual(detail.data["motorclub_summary"]["active_memberships"], 1)
        self.assertEqual(detail.data["motorclub_summary"]["pending_memberships"], 1)
        self.assertEqual(detail.data["motorclub_summary"]["psb_revenue"], "30.00")
        self.assertEqual(detail.data["motorclub_summary"]["tier_50_count"], 1)
        self.assertEqual(len(detail.data["motorclub_memberships"]), 1)
        self.assertEqual(detail.data["motorclub_memberships"][0]["plan_type"], "$50")

        active = self.client.get(
            reverse("api-owner-motorclub-memberships"),
            {"status": "active"},
        )
        self.assertEqual(active.status_code, status.HTTP_200_OK)
        self.assertEqual(len(active.data["memberships"]), 1)
        self.assertEqual(active.data["memberships"][0]["status"], "active")
        self.assertEqual(active.data["memberships"][0]["channel"], "direct")

        pending = self.client.get(
            reverse("api-owner-motorclub-memberships"),
            {"status": "pending"},
        )
        self.assertEqual(pending.status_code, status.HTTP_200_OK)
        self.assertEqual(len(pending.data["memberships"]), 1)
        self.assertEqual(pending.data["memberships"][0]["tier"], 75)

        bad = self.client.get(
            reverse("api-owner-motorclub-memberships"),
            {"status": "suspended"},
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_companion_space_books_detail_and_lists(self):
        from core.models import (
            InventoryProduct,
            KnowledgeHubMaterial,
            SpaceDocumentRecord,
            SpaceDocumentType,
        )
        from core.tlc_models import TLCPolicy

        inv_space = Space.objects.create(
            organization=self.org,
            key="custom_inventory",
            label="Kimo's Bikes",
            description="Inventory book",
        )
        docs_space = Space.objects.create(
            organization=self.org,
            key="documents",
            label="Documents",
            description="Vault",
        )
        kh_space = Space.objects.create(
            organization=self.org,
            key="knowledge_hub",
            label="Knowledge Hub",
            description="Training",
        )
        tlc_space = Space.objects.create(
            organization=self.org,
            key="tlc",
            label="TLC",
            description="TLC policies",
        )
        for space in (inv_space, docs_space, kh_space, tlc_space):
            self.owner_mem.accessible_spaces.add(space)

        InventoryProduct.objects.create(
            organization=self.org,
            space=inv_space,
            name="City Cruiser",
            sku="BIKE-01",
            quantity=3,
            low_stock_threshold=5,
            unit_price=Decimal("120.00"),
        )
        InventoryProduct.objects.create(
            organization=self.org,
            space=inv_space,
            name="Cargo Kit",
            sku="BIKE-02",
            quantity=0,
            low_stock_threshold=2,
            unit_price=Decimal("250.00"),
        )
        doc_type = SpaceDocumentType.objects.create(
            space=docs_space,
            organization=self.org,
            name="Registration",
        )
        SpaceDocumentRecord.objects.create(
            space=docs_space,
            organization=self.org,
            document_type=doc_type,
            order_number="ORD-1",
            quantity=1,
            added_by=self.agent,
        )
        KnowledgeHubMaterial.objects.create(
            space=kh_space,
            roadmap_name="DMV Rules",
            title="Plate Filing",
            description="How to file plates",
            step_number=1,
        )
        TLCPolicy.objects.create(
            organization=self.org,
            space=tlc_space,
            policy_number="TLC-100",
            named_insured="Midtown Limo",
            status=TLCPolicy.Status.ACTIVE,
            carrier="Lancer",
        )
        TLCPolicy.objects.create(
            organization=self.org,
            space=tlc_space,
            policy_number="TLC-200",
            named_insured="Queens Shuttle",
            status=TLCPolicy.Status.PENDING,
            carrier="Progressive",
        )

        self._auth(self.owner_token)

        inv_detail = self.client.get(reverse("api-owner-space-detail", args=[inv_space.id]))
        self.assertEqual(inv_detail.status_code, status.HTTP_200_OK)
        self.assertIn("inventory_summary", inv_detail.data)
        self.assertEqual(inv_detail.data["inventory_summary"]["total_products"], 2)
        self.assertEqual(len(inv_detail.data["inventory_items"]), 2)

        low = self.client.get(
            reverse("api-owner-inventory-products"),
            {"stock_status": "low_stock"},
        )
        self.assertEqual(low.status_code, status.HTTP_200_OK)
        self.assertEqual(len(low.data["items"]), 1)
        self.assertEqual(low.data["items"][0]["sku"], "BIKE-01")

        docs_detail = self.client.get(reverse("api-owner-space-detail", args=[docs_space.id]))
        self.assertEqual(docs_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(docs_detail.data["documents_summary"]["total_records"], 1)
        self.assertEqual(len(docs_detail.data["vault_documents"]), 1)

        kh_detail = self.client.get(reverse("api-owner-space-detail", args=[kh_space.id]))
        self.assertEqual(kh_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(kh_detail.data["knowledge_summary"]["total_materials"], 1)
        materials = self.client.get(
            reverse("api-owner-knowledge-materials"),
            {"roadmap": "DMV Rules"},
        )
        self.assertEqual(materials.status_code, status.HTTP_200_OK)
        self.assertEqual(len(materials.data["articles"]), 1)

        tlc_detail = self.client.get(reverse("api-owner-space-detail", args=[tlc_space.id]))
        self.assertEqual(tlc_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(tlc_detail.data["tlc_summary"]["active_policies"], 1)
        self.assertEqual(len(tlc_detail.data["tlc_policies"]), 1)
        pending = self.client.get(
            reverse("api-owner-tlc-policies"),
            {"status": "pending"},
        )
        self.assertEqual(pending.status_code, status.HTTP_200_OK)
        self.assertEqual(len(pending.data["policies"]), 1)
        self.assertEqual(pending.data["policies"][0]["policy_number"], "TLC-200")
