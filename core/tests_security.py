"""Regression tests for security hardening."""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Organization, OrganizationMembership, SiteNews, ServiceRecord


class APISecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="apiuser", password="password123")
        self.org = Organization.objects.create(name="API Org", city="NYC", is_active=True)
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True,
            role="owner",
        )

    def test_api_client_list_excludes_ssn(self):
        from core.models import Client

        Client.objects.create(
            organization=self.org,
            first_name="Secret",
            last_name="Client",
            gender="male",
            phone_number="7185550000",
            ssn="123-45-6789",
        )
        self.client.login(username="apiuser", password="password123")
        response = self.client.get("/api/clients/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload)
        first = payload[0] if isinstance(payload, list) else payload.get("results", [{}])[0]
        self.assertNotIn("ssn", first)

    def test_inactive_membership_cannot_access_api(self):
        inactive_user = User.objects.create_user(username="inactive", password="password123")
        OrganizationMembership.objects.create(
            user=inactive_user,
            organization=self.org,
            is_active=False,
            role="agent",
        )
        self.client.login(username="inactive", password="password123")
        response = self.client.get("/api/clients/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        count = payload if isinstance(payload, list) else payload.get("count", len(payload.get("results", [])))
        self.assertEqual(count, 0)


class SiteNewsSecurityTests(TestCase):
    def setUp(self):
        SiteNews.objects.create(title="Private", content="Staff only", is_active=True)

    def test_latest_news_requires_login(self):
        response = self.client.get(reverse("get-latest-news"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login/", response.url)


class IntakePOSTSecurityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="password123")
        self.org = Organization.objects.create(name="Intake Org", city="NYC", is_active=True)
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
        )

    def test_approve_intake_rejects_get(self):
        from core.models import ClientIntake

        intake = ClientIntake.objects.create(
            organization=self.org,
            first_name="Get",
            last_name="Blocked",
            gender="male",
            phone_number="7185550000",
            vin="GETBLOCKED0000001",
        )
        self.client.login(username="owner", password="password123")
        response = self.client.get(reverse("approve-intake", args=[intake.id]))
        self.assertEqual(response.status_code, 405)

    def test_send_reminder_rejects_get(self):
        from core.models import Client, Vehicle

        client = Client.objects.create(
            organization=self.org,
            first_name="Rem",
            last_name="Ind",
            gender="male",
            phone_number="7185550001",
        )
        vehicle = Vehicle.objects.create(
            client=client,
            vin="REMIND00000000001",
            vehicle_type="passenger",
            registration_expiration_date=date(2030, 1, 1),
        )
        self.client.login(username="owner", password="password123")
        response = self.client.get(reverse("send-manual-reminder", args=[vehicle.id]))
        self.assertEqual(response.status_code, 405)


class DeleteReceiptPermissionTests(TestCase):
    def setUp(self):
        from core.models import Client, ServiceRecord, Vehicle

        self.owner = User.objects.create_user(username="delowner", password="password123")
        self.agent = User.objects.create_user(username="delagent", password="password123")
        self.org = Organization.objects.create(name="Del Org", city="NYC", is_active=True)
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
        )
        OrganizationMembership.objects.create(
            user=self.agent,
            organization=self.org,
            is_active=True,
            role="agent",
            can_delete_receipt=False,
        )
        client = Client.objects.create(
            organization=self.org,
            first_name="Del",
            last_name="Client",
            gender="male",
            phone_number="7185550000",
        )
        vehicle = Vehicle.objects.create(
            client=client,
            vin="DELVIN00000000001",
            vehicle_type="passenger",
        )
        self.record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.owner,
            vehicle=vehicle,
            service_type="vehicle_registration",
        )

    def test_owner_can_delete_service_record(self):
        self.client.login(username="delowner", password="password123")
        response = self.client.post(reverse("delete-service-record", args=[self.record.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertFalse(ServiceRecord.objects.filter(id=self.record.id).exists())

    def test_agent_without_permission_cannot_delete(self):
        self.client.login(username="delagent", password="password123")
        response = self.client.post(reverse("delete-service-record", args=[self.record.id]))
        self.assertEqual(response.status_code, 403)
