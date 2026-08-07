from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client as TestClient, TestCase
from django.urls import reverse

from core.access import user_can_issue_refund
from core.finance_hub_metrics import build_daily_payment_cards
from core.models import Client, Organization, OrganizationMembership, ServiceRecord, Vehicle
from core.service_refunds import can_refund_service_record, issue_service_refund


class ServiceRefundTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="password123")
        self.agent = User.objects.create_user(username="agent", password="password123")
        self.org = Organization.objects.create(name="Refund Org", city="NYC", state="NY")
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
        )
        self.agent_membership = OrganizationMembership.objects.create(
            user=self.agent,
            organization=self.org,
            is_active=True,
            role="agent",
            can_issue_refund=False,
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Refund",
            last_name="Client",
            gender="male",
            phone_number="5550001111",
        )
        self.vehicle = Vehicle.objects.create(
            client=self.client_obj,
            vin="1HGBH41JXMN109199",
            vehicle_number="VEH-REF-001",
        )
        self.tx_date = date(2026, 6, 10)
        self.record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.owner,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            status="completed",
            transaction_type="transmittal",
            processing_fee=Decimal("100.00"),
            paid_amount=Decimal("75.00"),
            payment_method="cash",
            transaction_date=self.tx_date,
        )
        self.http = TestClient()

    def test_user_can_issue_refund_requires_permission(self):
        self.assertTrue(user_can_issue_refund(self.owner, self.org.id))
        self.assertFalse(user_can_issue_refund(self.agent, self.org.id))

        self.agent_membership.can_issue_refund = True
        self.agent_membership.save(update_fields=["can_issue_refund"])
        self.assertTrue(user_can_issue_refund(self.agent, self.org.id))

    def test_issue_service_refund_creates_refund_row_and_reduces_original(self):
        refund = issue_service_refund(self.record, recorded_by=self.owner)

        self.record.refresh_from_db()
        self.assertEqual(self.record.paid_amount, Decimal("0"))
        self.assertEqual(refund.status, "refund")
        self.assertEqual(refund.refunded_from_id, self.record.id)
        self.assertEqual(refund.vehicle_id, self.vehicle.id)
        self.assertEqual(refund.transaction_date, self.tx_date)
        self.assertEqual(refund.paid_amount, Decimal("75.00"))
        self.assertFalse(can_refund_service_record(self.record))

    def test_refund_endpoint_requires_permission(self):
        self.http.login(username="agent", password="password123")
        response = self.http.post(reverse("issue-service-refund", args=[self.record.id]))
        self.assertEqual(response.status_code, 403)

    def test_refund_endpoint_success_for_permitted_agent(self):
        self.agent_membership.can_issue_refund = True
        self.agent_membership.save(update_fields=["can_issue_refund"])
        self.http.login(username="agent", password="password123")

        response = self.http.post(reverse("issue-service-refund", args=[self.record.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")

        self.record.refresh_from_db()
        self.assertEqual(self.record.paid_amount, Decimal("0"))
        self.assertEqual(
            ServiceRecord.objects.filter(vehicle=self.vehicle, status="refund").count(),
            1,
        )

    def test_refund_reduces_daily_payment_cards_for_transaction_date(self):
        records = ServiceRecord.objects.filter(organization=self.org, deleted_at__isnull=True)
        cards_before, total_before = build_daily_payment_cards(
            records, self.tx_date
        )
        self.assertEqual(total_before, Decimal("75.00"))

        issue_service_refund(self.record, recorded_by=self.owner)

        cards_after, total_after = build_daily_payment_cards(
            records, self.tx_date
        )
        self.assertEqual(total_after, Decimal("0.00"))
        self.assertLess(total_after, total_before)

    def test_vehicle_detail_shows_refund_button_only_with_permission(self):
        self.http.login(username="agent", password="password123")
        response = self.http.get(reverse("vehicle-detail", args=[self.vehicle.id]))
        self.assertNotContains(response, "btn-refund-receipt")

        self.agent_membership.can_issue_refund = True
        self.agent_membership.save(update_fields=["can_issue_refund"])
        response = self.http.get(reverse("vehicle-detail", args=[self.vehicle.id]))
        self.assertContains(response, "btn-refund-receipt")
