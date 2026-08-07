from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client as TestClient, TestCase
from django.urls import reverse

from core.models import (
    Client,
    DailyPaymentTransaction,
    Organization,
    OrganizationMembership,
    Space,
)


class DailyPaymentEditTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Daily Pay Org", city="NYC")
        self.space = Space.objects.create(
            organization=self.org,
            label="Insurance Space",
            key="insurance",
        )
        self.banker = User.objects.create_user(username="banker", password="password123")
        self.agent = User.objects.create_user(username="agent", password="password123")
        self.banker_membership = OrganizationMembership.objects.create(
            user=self.banker,
            organization=self.org,
            is_active=True,
            role="owner",
            can_deal_with_insurance=True,
            can_view_spaces=True,
            can_view_banking=True,
        )
        self.banker_membership.accessible_spaces.add(self.space)
        OrganizationMembership.objects.create(
            user=self.agent,
            organization=self.org,
            is_active=True,
            role="agent",
            can_deal_with_insurance=True,
            can_view_spaces=True,
            can_view_banking=False,
        ).accessible_spaces.add(self.space)
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Daily",
            last_name="Client",
        )
        self.tx_date = date(2026, 6, 12)
        self.payment = DailyPaymentTransaction.objects.create(
            organization=self.org,
            client=self.client_obj,
            transaction_date=self.tx_date,
            amount=Decimal("120.00"),
            payment_type="new_business",
            payment_method="cash",
            recorded_by=self.banker,
            notes="Original note",
        )
        self.http = TestClient()

    def test_edit_daily_payment_requires_banking_access(self):
        self.http.login(username="agent", password="password123")
        response = self.http.post(
            reverse("edit-daily-payment", args=[self.payment.id]),
            {
                "client_name": "Daily Client",
                "amount": "150.00",
                "payment_type": "renewal",
                "payment_method": "zelle",
                "transaction_date": self.tx_date.isoformat(),
                "notes": "Should fail",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal("120.00"))
        self.assertIsNone(self.payment.updated_by_id)

    def test_edit_daily_payment_updates_record_and_editor(self):
        self.http.login(username="banker", password="password123")
        response = self.http.post(
            reverse("edit-daily-payment", args=[self.payment.id]),
            {
                "client_name": "Daily Client",
                "amount": "150.00",
                "payment_type": "renewal",
                "payment_method": "zelle",
                "transaction_date": self.tx_date.isoformat(),
                "notes": "Updated note",
                "is_cleared": "1",
                "cleared_date": self.tx_date.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal("150.00"))
        self.assertEqual(self.payment.payment_type, "renewal")
        self.assertEqual(self.payment.payment_method, "zelle")
        self.assertEqual(self.payment.notes, "Updated note")
        self.assertTrue(self.payment.is_cleared)
        self.assertEqual(self.payment.updated_by_id, self.banker.id)
        self.assertIsNotNone(self.payment.updated_at)

    def test_daily_payments_tab_shows_edit_controls_for_banking_users_only(self):
        self.http.login(username="banker", password="password123")
        response = self.http.get(
            reverse("inventory-detail", args=[self.space.id]),
            {"tab": "daily-payments", "daily_date": self.tx_date.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edited By")
        self.assertContains(response, 'class="dpt-edit-btn"')

        self.http.login(username="agent", password="password123")
        response = self.http.get(
            reverse("inventory-detail", args=[self.space.id]),
            {"tab": "daily-payments", "daily_date": self.tx_date.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<th>Edited By</th>")
        self.assertNotContains(response, 'class="dpt-edit-btn"')
        self.assertNotContains(response, "editDailyPaymentModal")
