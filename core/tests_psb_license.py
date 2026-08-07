"""Tests for PSB (Organization) license status and renewal alerts."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Notification, Organization, OrganizationMembership
from core.psb_license import psb_license_status, sync_psb_license_alerts

User = get_user_model()


class PsbLicenseTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="PSB License Org", city="NY", state="NY")
        self.owner = User.objects.create_user(username="psb_lic_owner", password="pass")
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.agent = User.objects.create_user(username="psb_lic_agent", password="pass")
        OrganizationMembership.objects.create(
            user=self.agent,
            organization=self.org,
            role=OrganizationMembership.Role.AGENT,
            is_active=True,
        )
        self.today = date(2026, 7, 16)

    def test_status_ok_outside_window(self):
        self.org.psbc_license_expiration_date = self.today + timedelta(days=20)
        self.org.save(update_fields=["psbc_license_expiration_date"])
        status = psb_license_status(self.org, today=self.today)
        self.assertEqual(status["state"], "ok")
        self.assertFalse(status["needs_alert"])

    def test_status_expiring_within_alert_days(self):
        self.org.psbc_license_alert_days = 5
        self.org.psbc_license_expiration_date = self.today + timedelta(days=3)
        self.org.save(update_fields=["psbc_license_alert_days", "psbc_license_expiration_date"])
        status = psb_license_status(self.org, today=self.today)
        self.assertEqual(status["state"], "expiring")
        self.assertTrue(status["needs_alert"])
        self.assertEqual(status["days_left"], 3)

    def test_status_expired(self):
        self.org.psbc_license_expiration_date = self.today - timedelta(days=2)
        self.org.save(update_fields=["psbc_license_expiration_date"])
        status = psb_license_status(self.org, today=self.today)
        self.assertEqual(status["state"], "expired")
        self.assertTrue(status["needs_alert"])

    def test_missing_expiration_creates_no_alert(self):
        result = sync_psb_license_alerts(self.org, today=self.today)
        self.assertEqual(result["created"], 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_sync_creates_one_alert_per_owner_and_dedupes(self):
        self.org.psbc_license = "PSB-1"
        self.org.psbc_license_expiration_date = self.today + timedelta(days=2)
        self.org.save(update_fields=["psbc_license", "psbc_license_expiration_date"])
        first = sync_psb_license_alerts(self.org, today=self.today)
        second = sync_psb_license_alerts(self.org, today=self.today)
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 1)
        notif = Notification.objects.get()
        self.assertEqual(notif.event_type, "psb_license_expiring")
        self.assertEqual(notif.organization_id, self.org.id)
        self.assertIsNone(notif.client_id)
        self.assertIsNone(notif.insurance_company_id)
        self.assertEqual(notif.user_id, self.owner.id)

    def test_renewal_clears_open_alerts(self):
        self.org.psbc_license_expiration_date = self.today + timedelta(days=1)
        self.org.save(update_fields=["psbc_license_expiration_date"])
        sync_psb_license_alerts(self.org, today=self.today)
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 1)

        self.org.psbc_license_expiration_date = self.today + timedelta(days=60)
        self.org.save(update_fields=["psbc_license_expiration_date"])
        result = sync_psb_license_alerts(self.org, today=self.today)
        self.assertEqual(result["state"], "ok")
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 0)

    def test_edit_psb_license_owner_only(self):
        self.client.login(username="psb_lic_owner", password="pass")
        expiration = (timezone.localdate() + timedelta(days=2)).isoformat()
        response = self.client.post(
            reverse("edit-psb-license"),
            {
                "organization_id": str(self.org.id),
                "psbc_license": "PSBC-999",
                "psbc_license_effective_date": "2026-01-01",
                "psbc_license_expiration_date": expiration,
                "psbc_license_alert_days": "5",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.psbc_license, "PSBC-999")
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 1)

        notif = Notification.objects.get()
        open_resp = self.client.get(reverse("open-notification", args=[notif.id]))
        self.assertEqual(open_resp.status_code, 302)
        self.assertIn("/dashboard/", open_resp.url)

    def test_agent_cannot_edit_psb_license(self):
        self.client.login(username="psb_lic_agent", password="pass")
        response = self.client.post(
            reverse("edit-psb-license"),
            {
                "organization_id": str(self.org.id),
                "psbc_license": "HACK",
                "psbc_license_effective_date": "2026-01-01",
                "psbc_license_expiration_date": "2026-12-01",
                "psbc_license_alert_days": "5",
            },
        )
        self.assertIn(response.status_code, (302, 403))
        self.org.refresh_from_db()
        self.assertEqual(self.org.psbc_license, "")

    def test_rejects_expiration_before_effective(self):
        self.client.login(username="psb_lic_owner", password="pass")
        response = self.client.post(
            reverse("edit-psb-license"),
            {
                "organization_id": str(self.org.id),
                "psbc_license": "X",
                "psbc_license_effective_date": "2026-06-01",
                "psbc_license_expiration_date": "2026-05-01",
                "psbc_license_alert_days": "5",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.psbc_license, "")

    def test_dashboard_shows_psb_license_alert(self):
        self.org.psbc_license = "PSB-ALERT"
        self.org.psbc_license_expiration_date = timezone.localdate() + timedelta(days=2)
        self.org.save(update_fields=["psbc_license", "psbc_license_expiration_date"])
        self.client.login(username="psb_lic_owner", password="pass")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PSB license renewal action")
        self.assertContains(response, "PSB License Org")
