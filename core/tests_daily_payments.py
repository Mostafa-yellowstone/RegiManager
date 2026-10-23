from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client as TestClient, TestCase, override_settings
from django.urls import reverse

from core.models import (
    Client,
    DailyPaymentTransaction,
    Organization,
    OrganizationMembership,
    Space,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
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
                "client_id": str(self.client_obj.id),
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
                "client_id": str(self.client_obj.id),
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

    def test_add_daily_payment_requires_existing_client_id(self):
        self.http.login(username="banker", password="password123")
        from core.models import InsuranceCompany

        company = InsuranceCompany.objects.create(
            organization=self.org,
            name="Carrier Co",
        )
        before = Client.objects.filter(organization=self.org).count()
        response = self.http.post(
            reverse("add-daily-payment"),
            {
                "organization": str(self.org.id),
                "client_name": "Brand New Person",
                "insurance_company": str(company.id),
                "amount": "50.00",
                "payment_type": "monthly_payment",
                "payment_method": "cash",
                "transaction_date": self.tx_date.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Client.objects.filter(organization=self.org).count(), before)
        self.assertFalse(
            DailyPaymentTransaction.objects.filter(
                organization=self.org,
                amount=Decimal("50.00"),
            ).exists()
        )

    def test_add_daily_payment_with_client_id_succeeds(self):
        self.http.login(username="banker", password="password123")
        from core.models import InsuranceCompany

        company = InsuranceCompany.objects.create(
            organization=self.org,
            name="Carrier Co",
        )
        response = self.http.post(
            reverse("add-daily-payment"),
            {
                "organization": str(self.org.id),
                "client_id": str(self.client_obj.id),
                "insurance_company": str(company.id),
                "amount": "75.00",
                "payment_type": "monthly_payment",
                "payment_method": "cash",
                "transaction_date": self.tx_date.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        payment = DailyPaymentTransaction.objects.get(
            organization=self.org,
            amount=Decimal("75.00"),
        )
        self.assertEqual(payment.client_id, self.client_obj.id)

    def test_daily_payments_tab_shows_edit_controls_for_banking_users_only(self):
        self.http.login(username="banker", password="password123")
        response = self.http.get(
            reverse("inventory-detail", args=[self.space.id]),
            {"tab": "daily-payments", "daily_date": self.tx_date.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edited By")
        self.assertContains(response, 'class="dpt-edit-btn"')
        self.assertContains(response, "addDailyClientSearch")
        self.assertContains(response, "Search existing client")

        self.http.login(username="agent", password="password123")
        response = self.http.get(
            reverse("inventory-detail", args=[self.space.id]),
            {"tab": "daily-payments", "daily_date": self.tx_date.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<th>Edited By</th>")
        self.assertNotContains(response, 'class="dpt-edit-btn"')
        self.assertNotContains(response, "editDailyPaymentModal")
        self.assertContains(response, "addDailyClientSearch")


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class DailyPaymentFilterTests(TestCase):
    def setUp(self):
        from core.models import InsuranceCompany

        self.org = Organization.objects.create(name="Filter Org", city="NYC")
        self.space = Space.objects.create(organization=self.org, label="Insurance Space", key="insurance")
        self.user = User.objects.create_user(username="filterer", password="password123")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True,
            role="owner",
            can_deal_with_insurance=True,
            can_view_spaces=True,
            can_view_banking=True,
        ).accessible_spaces.add(self.space)
        self.client_obj = Client.objects.create(organization=self.org, first_name="Range", last_name="Client")
        self.acme = InsuranceCompany.objects.create(organization=self.org, name="Acme Mutual")
        self.zen = InsuranceCompany.objects.create(organization=self.org, name="Zen Insurance")
        self.june_1 = self._pay(date(2026, 6, 1), "10.00", self.acme)
        self.june_12 = self._pay(date(2026, 6, 12), "20.00", self.zen)
        self.july_5 = self._pay(date(2026, 7, 5), "30.00", self.acme)
        self.http = TestClient()
        self.http.login(username="filterer", password="password123")
        self.url = reverse("inventory-detail", args=[self.space.id])

    def _pay(self, when, amount, company):
        return DailyPaymentTransaction.objects.create(
            organization=self.org,
            client=self.client_obj,
            insurance_company=company,
            transaction_date=when,
            amount=Decimal(amount),
            payment_type="new_business",
            payment_method="cash",
            recorded_by=self.user,
        )

    def _ids(self, response):
        return {tx.id for tx in response.context["daily_transactions"]}

    def test_period_returns_every_payment_in_range(self):
        response = self.http.get(self.url, {"tab": "daily-payments", "daily_from": "2026-06-01", "daily_to": "2026-06-30"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["daily_is_range"])
        self.assertEqual(self._ids(response), {self.june_1.id, self.june_12.id})
        self.assertEqual(response.context["daily_grand_total"], Decimal("30.00"))
        self.assertContains(response, "Jun 1, 2026 – Jun 30, 2026")

    def test_company_filter_within_period(self):
        response = self.http.get(self.url, {
            "tab": "daily-payments", "daily_from": "2026-06-01", "daily_to": "2026-07-31",
            "daily_company": str(self.acme.id),
        })
        self.assertEqual(self._ids(response), {self.june_1.id, self.july_5.id})

    def test_filters_survive_plain_revisit_and_reset_clears_them(self):
        self.http.get(self.url, {
            "tab": "daily-payments", "daily_from": "2026-06-01", "daily_to": "2026-07-31",
            "daily_company": str(self.zen.id),
        })
        response = self.http.get(self.url, {"tab": "daily-payments"})
        self.assertTrue(response.context["daily_is_range"])
        self.assertEqual(self._ids(response), {self.june_12.id})

        response = self.http.get(self.url, {"tab": "daily-payments", "daily_reset": "1"})
        self.assertFalse(response.context["daily_is_range"])
        self.assertEqual(response.context["daily_filters"], {})

    def test_picking_a_day_leaves_period_but_keeps_company(self):
        self.http.get(self.url, {
            "tab": "daily-payments", "daily_from": "2026-06-01", "daily_to": "2026-07-31",
            "daily_company": str(self.acme.id),
        })
        response = self.http.get(self.url, {"tab": "daily-payments", "daily_date": "2026-07-05"})
        self.assertFalse(response.context["daily_is_range"])
        self.assertEqual(self._ids(response), {self.july_5.id})
        self.assertEqual(response.context["daily_company_filter"], str(self.acme.id))

    def test_single_day_selection_expires_next_day(self):
        self.http.get(self.url, {"tab": "daily-payments", "daily_date": "2026-06-12"})
        session = self.http.session
        key = f"daily_payment_filters:{self.org.id}"
        payload = session[key]
        payload["saved_on"] = "2000-01-01"
        session[key] = payload
        session.save()
        response = self.http.get(self.url, {"tab": "daily-payments"})
        from django.utils import timezone

        self.assertEqual(response.context["daily_payment_date"], timezone.localdate())

    def test_pagination_keeps_filters(self):
        for day in range(1, 29):
            for _ in range(2):
                self._pay(date(2026, 2, day), "1.00", self.acme)
        params = {"tab": "daily-payments", "daily_from": "2026-02-01", "daily_to": "2026-02-28", "daily_company": str(self.acme.id)}
        response = self.http.get(self.url, params)
        page = response.context["daily_page_obj"]
        self.assertEqual(page.paginator.count, 56)
        self.assertEqual(len(response.context["daily_transactions"]), 50)
        self.assertEqual(response.context["daily_grand_total"], Decimal("56.00"))
        self.assertIn(f"daily_company={self.acme.id}", response.context["daily_filter_qs"])
        self.assertContains(response, "daily_page=2")

        response = self.http.get(self.url, {"tab": "daily-payments", "daily_page": "2"})
        self.assertEqual(len(response.context["daily_transactions"]), 6)
        self.assertTrue(response.context["daily_is_range"])

    def test_delete_returns_to_filtered_page(self):
        back = f"{self.url}?tab=daily-payments&daily_from=2026-06-01&daily_to=2026-06-30&daily_page=1"
        response = self.http.get(reverse("delete-daily-payment", args=[self.june_1.id]), {"next": back})
        self.assertRedirects(response, back, fetch_redirect_response=False)
