"""Tests for insurance company license status and renewal alerts."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.insurance_company_license import (
    company_license_status,
    sync_company_license_alerts,
)
from core.models import (
    InsuranceCompany,
    Notification,
    Organization,
    OrganizationMembership,
    Space,
)

User = get_user_model()


class InsuranceCompanyLicenseTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="License Org", city="NY", state="NY")
        Space.objects.create(organization=self.org, key="insurance", label="Insurance")
        self.owner = User.objects.create_user(username="lic_owner", password="pass")
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            can_deal_with_insurance=True,
            is_active=True,
        )
        self.company = InsuranceCompany.objects.create(
            organization=self.org,
            name="Progressive Test",
            license_alert_days=5,
        )
        self.today = date(2026, 7, 16)

    def test_status_ok_outside_window(self):
        self.company.license_expiration_date = self.today + timedelta(days=20)
        self.company.save(update_fields=["license_expiration_date"])
        status = company_license_status(self.company, today=self.today)
        self.assertEqual(status["state"], "ok")
        self.assertFalse(status["needs_alert"])

    def test_status_expiring_within_alert_days(self):
        self.company.license_expiration_date = self.today + timedelta(days=3)
        self.company.save(update_fields=["license_expiration_date"])
        status = company_license_status(self.company, today=self.today)
        self.assertEqual(status["state"], "expiring")
        self.assertTrue(status["needs_alert"])
        self.assertEqual(status["days_left"], 3)

    def test_status_expired(self):
        self.company.license_expiration_date = self.today - timedelta(days=2)
        self.company.save(update_fields=["license_expiration_date"])
        status = company_license_status(self.company, today=self.today)
        self.assertEqual(status["state"], "expired")
        self.assertTrue(status["needs_alert"])

    def test_missing_expiration_creates_no_alert(self):
        result = sync_company_license_alerts(self.company, today=self.today)
        self.assertEqual(result["created"], 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_sync_creates_one_alert_per_user_and_dedupes(self):
        self.company.license_number = "LIC-1"
        self.company.license_expiration_date = self.today + timedelta(days=2)
        self.company.save(update_fields=["license_number", "license_expiration_date"])
        first = sync_company_license_alerts(self.company, today=self.today)
        second = sync_company_license_alerts(self.company, today=self.today)
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 1)
        notif = Notification.objects.get()
        self.assertEqual(notif.event_type, "company_license_expiring")
        self.assertEqual(notif.insurance_company_id, self.company.id)
        self.assertIsNone(notif.client_id)

    def test_renewal_clears_open_alerts(self):
        self.company.license_expiration_date = self.today + timedelta(days=1)
        self.company.save(update_fields=["license_expiration_date"])
        sync_company_license_alerts(self.company, today=self.today)
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 1)

        self.company.license_expiration_date = self.today + timedelta(days=60)
        self.company.save(update_fields=["license_expiration_date"])
        result = sync_company_license_alerts(self.company, today=self.today)
        self.assertEqual(result["state"], "ok")
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 0)

    def test_edit_license_view_and_open_notification(self):
        self.client.login(username="lic_owner", password="pass")
        response = self.client.post(
            reverse("edit-insurance-company-license", args=[self.company.id]),
            {
                "license_number": "BR-999",
                "license_effective_date": "2026-01-01",
                "license_expiration_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
                "license_alert_days": "5",
                "broker_arrangement": "br",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.company.refresh_from_db()
        self.assertEqual(self.company.license_number, "BR-999")
        self.assertEqual(self.company.broker_arrangement, "br")
        self.assertTrue(self.company.takes_broker_fees)
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 1)

        notif = Notification.objects.get()
        open_resp = self.client.get(reverse("open-notification", args=[notif.id]))
        self.assertEqual(open_resp.status_code, 302)
        self.assertIn(f"/company/{self.company.id}/", open_resp.url)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)
        # Visiting company detail syncs alerts but must not recreate a dismissed Ref.
        detail = self.client.get(reverse("insurance-company-detail", args=[self.company.id]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 0)

    def test_rejects_expiration_before_effective(self):
        self.client.login(username="lic_owner", password="pass")
        response = self.client.post(
            reverse("edit-insurance-company-license", args=[self.company.id]),
            {
                "license_number": "X",
                "license_effective_date": "2026-06-01",
                "license_expiration_date": "2026-05-01",
                "license_alert_days": "5",
                "broker_arrangement": "bc",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.company.refresh_from_db()
        self.assertEqual(self.company.license_number, "")
        self.assertFalse(self.company.broker_arrangement)
