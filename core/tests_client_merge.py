from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.client_merge import ClientMergeError, merge_clients
from core.models import (
    Client,
    ClientNote,
    InsuranceCompany,
    InsurancePolicy,
    Organization,
    OrganizationMembership,
    ServiceRecord,
    Vehicle,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ClientMergeTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Merge Office")
        self.other_org = Organization.objects.create(name="Other Office")
        self.agent = User.objects.create_user(username="mergeagent", password="password123")
        OrganizationMembership.objects.create(
            user=self.agent,
            organization=self.org,
            role=OrganizationMembership.Role.AGENT,
            is_active=True,
        )
        self.dmv = Client.objects.create(
            organization=self.org,
            first_name="Sam",
            last_name="Rivera",
            driver_license="D1234567",
            phone_number="5551112222",
            street_address="10 Main St",
            city="Brooklyn",
            state="NY",
            zip_code="11201",
        )
        self.insurance = Client.objects.create(
            organization=self.org,
            first_name="Sam",
            last_name="Rivera",
            email="sam@example.com",
            ssn="111-22-3333",
            phone_number="5559990000",
        )
        self.vehicle = Vehicle.objects.create(
            client=self.dmv,
            vin="1HGBH41JXMN109186",
            plate_number="ABC1234",
        )
        self.record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.agent,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            client_name="Old Snapshot",
        )
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Acme")
        self.policy = InsurancePolicy.objects.create(
            organization=self.org,
            client=self.insurance,
            insurance_company=self.company,
            policy_number="POL-MERGE",
            premium=Decimal("500.00"),
            commission_rate=Decimal("10.00"),
            commission_amount=Decimal("50.00"),
            start_date=date(2026, 1, 1),
            end_date=date(2027, 1, 1),
        )
        ClientNote.objects.create(client=self.insurance, content="Insurance follow-up")

    def test_merge_moves_insurance_onto_dmv_profile(self):
        merge_clients(self.dmv, self.insurance, actor=self.agent)
        self.dmv.refresh_from_db()

        self.assertEqual(self.dmv.email, "sam@example.com")
        self.assertEqual(self.dmv.ssn, "111-22-3333")
        self.assertEqual(self.dmv.phone_number, "5551112222")
        self.assertEqual(self.dmv.driver_license, "D1234567")
        self.assertFalse(Client.objects.filter(pk=self.insurance.pk).exists())
        self.assertTrue(Client.all_objects.filter(pk=self.insurance.pk, deleted_at__isnull=False).exists())

        self.policy.refresh_from_db()
        self.vehicle.refresh_from_db()
        self.record.refresh_from_db()
        self.assertEqual(self.policy.client_id, self.dmv.pk)
        self.assertEqual(self.vehicle.client_id, self.dmv.pk)
        self.assertEqual(self.record.client_name, "Sam Rivera")
        self.assertTrue(ClientNote.objects.filter(client=self.dmv, content="Insurance follow-up").exists())
        self.assertTrue(ClientNote.objects.filter(client=self.dmv, content__contains="Merged profile").exists())

    def test_same_vin_folds_into_one_vehicle(self):
        Vehicle.objects.create(client=self.insurance, vin="1HGBH41JXMN109186", plate_number="XYZ999")
        merge_clients(self.dmv, self.insurance, actor=self.agent)
        vehicles = list(Vehicle.objects.filter(client=self.dmv))
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0].vin, "1HGBH41JXMN109186")

    def test_refuses_a_different_office(self):
        outsider = Client.objects.create(organization=self.other_org, first_name="Other", last_name="Person")
        with self.assertRaises(ClientMergeError):
            merge_clients(self.dmv, outsider, actor=self.agent)

    def test_agent_can_merge_from_the_profile(self):
        self.client.login(username="mergeagent", password="password123")
        page = self.client.get(reverse("client-detail", args=[self.dmv.id]))
        self.assertContains(page, "Merge profiles")

        response = self.client.post(
            reverse("merge-client-profiles", args=[self.dmv.id]),
            {"other_client_id": self.insurance.id},
        )
        self.assertRedirects(response, reverse("client-detail", args=[self.dmv.id]))
        self.assertFalse(Client.objects.filter(pk=self.insurance.pk).exists())
        self.assertEqual(InsurancePolicy.objects.get(pk=self.policy.pk).client_id, self.dmv.pk)
