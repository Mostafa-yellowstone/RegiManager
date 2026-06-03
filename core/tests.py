from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth.models import User
from decimal import Decimal
from core.models import Organization, OrganizationMembership, Client, InsuranceCompany, InsurancePolicy, Space, Vehicle

class InsuranceSpaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password123")
        self.org = Organization.objects.create(name="Test Org", city="NYC")
        # Assign membership so _get_user_organizations returns this org
        OrganizationMembership.objects.create(user=self.user, organization=self.org, is_active=True, role="owner")
        
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Allstate")
        self.client = TestClient()
        self.client.login(username="testuser", password="password123")

    def test_add_policy_creates_client_if_not_exists(self):
        # We start with 0 clients in the organization
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 0)
        
        response = self.client.post(reverse("add-insurance-policy"), {
            "organization": self.org.id,
            "client_name": "John Doe",
            "insurance_company": self.company.id,
            "policy_number": "POL-999",
            "premium": "1200.00",
            "commission_rate": "10.00",
            "status": "active",
            "start_date": "2026-06-01",
            "end_date": "2026-12-01",
            "insurance_period_months": "6",
        })
        
        # Verify the client was automatically created
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 1)
        new_client = Client.objects.filter(organization=self.org).first()
        self.assertEqual(new_client.first_name, "John")
        self.assertEqual(new_client.last_name, "Doe")
        
        # Verify the policy is associated with this new client
        policy = InsurancePolicy.objects.filter(organization=self.org).first()
        self.assertIsNotNone(policy)
        self.assertEqual(policy.client, new_client)
        self.assertEqual(policy.policy_number, "POL-999")
        self.assertEqual(policy.premium, Decimal("1200.00"))
        self.assertEqual(policy.commission_amount, Decimal("120.00"))

    def test_add_policy_uses_existing_client_if_exists(self):
        # Create an existing client
        existing_client = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Smith",
            source="walk-in"
        )
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 1)
        
        response = self.client.post(reverse("add-insurance-policy"), {
            "organization": self.org.id,
            "client_name": "Jane Smith",
            "insurance_company": self.company.id,
            "policy_number": "POL-888",
            "premium": "1000.00",
            "commission_rate": "15.00",
            "status": "active",
            "start_date": "2026-06-01",
            "end_date": "2026-12-01",
            "insurance_period_months": "6",
        })
        
        # Check that no new client was created
        self.assertEqual(Client.objects.filter(organization=self.org).count(), 1)
        
        # Verify the policy uses the existing client
        policy = InsurancePolicy.objects.filter(organization=self.org).first()
        self.assertEqual(policy.client, existing_client)


class VehicleSoftDeleteTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", city="NYC")
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Smith",
            source="walk-in"
        )

    def test_soft_deleted_vehicle_allows_duplicate_vin(self):
        # 1. Create first vehicle
        v1 = Vehicle.objects.create(
            client=self.client_obj,
            vin="1234567890ABCDEFG",
            year=2020,
            make="Toyota",
            model="Camry"
        )
        
        # 2. Soft-delete the first vehicle
        v1.delete()
        self.assertIsNotNone(v1.deleted_at)
        
        # 3. Create second vehicle with the same VIN (should succeed)
        v2 = Vehicle.objects.create(
            client=self.client_obj,
            vin="1234567890ABCDEFG",
            year=2022,
            make="Toyota",
            model="Rav4"
        )
        self.assertEqual(v2.vin, "1234567890ABCDEFG")
        
        # 4. Attempt to create a third vehicle with the same VIN while v2 is still active (should fail)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Vehicle.objects.create(
                client=self.client_obj,
                vin="1234567890ABCDEFG",
                year=2023,
                make="Toyota",
                model="Prius"
            )

