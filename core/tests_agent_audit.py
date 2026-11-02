from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.test import Client as TestClient
from django.urls import reverse

from core.models import Organization, OrganizationMembership, ServiceRecord


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class AgentAuditTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Audit Org", city="NYC")
        self.owner = User.objects.create_user(username="auditowner", password="password123", first_name="Owen")
        self.agent_user = User.objects.create_user(username="audithand", password="password123", first_name="Ada", last_name="Lane")
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
            can_view_spaces=True,
        )
        self.agent = OrganizationMembership.objects.create(
            user=self.agent_user,
            organization=self.org,
            is_active=True,
            role="agent",
            can_view_spaces=True,
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.agent_user,
            service_type="vehicle_registration",
            status="completed",
            client_name="January Client",
            receipt_number="RCPT-AUDIT-JAN",
            transaction_date=date(2026, 1, 15),
            dmv_fee=Decimal("25.00"),
            processing_fee=Decimal("15.00"),
            plate_number="JAN111",
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.agent_user,
            service_type="new_plates",
            status="failed",
            client_name="March Client",
            receipt_number="RCPT-AUDIT-MAR",
            transaction_date=date(2026, 3, 2),
            dmv_fee=Decimal("50.00"),
            processing_fee=Decimal("30.00"),
            plate_number="MAR222",
        )
        self.client = TestClient()
        self.client.login(username="auditowner", password="password123")

    def test_directory_and_profile_cover_the_whole_window(self):
        directory = self.client.get(reverse("all-agents-directory"), {"period": "all"})
        self.assertEqual(directory.status_code, 200)
        self.assertContains(directory, "Ada Lane")
        self.assertContains(directory, "All time")
        self.assertContains(directory, "Open audit")

        profile = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all"},
        )
        self.assertEqual(profile.status_code, 200)
        self.assertContains(profile, "RCPT-AUDIT-JAN")
        self.assertContains(profile, "RCPT-AUDIT-MAR")
        self.assertContains(profile, "Export Excel")

        january = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "custom", "start_date": "2026-01-01", "end_date": "2026-01-31"},
        )
        self.assertContains(january, "RCPT-AUDIT-JAN")
        self.assertNotContains(january, "RCPT-AUDIT-MAR")

        exported = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all", "export": "xlsx"},
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("spreadsheetml", exported["Content-Type"])
        self.assertIn(b"PK", exported.content[:2])

    def test_advanced_audit_filters_service_type_payment_fee_notes(self):
        # Service type filter
        resp_service = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all", "service_type": "vehicle_registration"},
        )
        self.assertEqual(resp_service.status_code, 200)
        self.assertContains(resp_service, "RCPT-AUDIT-JAN")
        self.assertNotContains(resp_service, "RCPT-AUDIT-MAR")

        # Status filter
        resp_status = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all", "status": "failed"},
        )
        self.assertEqual(resp_status.status_code, 200)
        self.assertContains(resp_status, "RCPT-AUDIT-MAR")
        self.assertNotContains(resp_status, "RCPT-AUDIT-JAN")

        # Fee range filter
        resp_fee = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all", "min_fee": "50.00"},
        )
        self.assertEqual(resp_fee.status_code, 200)
        self.assertContains(resp_fee, "RCPT-AUDIT-MAR")
        self.assertNotContains(resp_fee, "RCPT-AUDIT-JAN")

        # Sorting filter
        resp_sort = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all", "sort": "-service_fee"},
        )
        self.assertEqual(resp_sort.status_code, 200)
        page_records = list(resp_sort.context["page_obj"])
        self.assertEqual(page_records[0].receipt_number, "RCPT-AUDIT-MAR")
        self.assertEqual(page_records[1].receipt_number, "RCPT-AUDIT-JAN")
