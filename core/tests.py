from datetime import date

from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth.models import User
from decimal import Decimal
from core.models import Organization, OrganizationMembership, Client, InsuranceCompany, InsurancePolicy, Space, Vehicle, ServiceRecord, Referral
from core.forms import ClientForm
from core.client_referral import apply_client_referral_from_form
from core.client_search import build_full_client_search_q, build_client_name_search_q
from core.dashboard_metrics import build_service_cards
from core.finance_hub_metrics import build_daily_payment_cards, build_month_goal_forecast

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
            "stage": "bound",
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
            "stage": "bound",
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

    def test_add_policy_with_new_fields(self):
        response = self.client.post(reverse("add-insurance-policy"), {
            "organization": self.org.id,
            "client_name": "New Field Client",
            "insurance_company": self.company.id,
            "policy_number": "POL-NEW-111",
            "premium": "1500.00",
            "commission_rate": "12.50",
            "stage": "bound",
            "status": "pending",
            "insurance_type": "commercial_auto",
            "source": "google_search",
            "business_type": "renewal",
            "bound_date": "2026-06-04",
            "start_date": "2026-06-05",
            "end_date": "2026-12-05",
            "insurance_period_months": "6",
        })
        policy = InsurancePolicy.objects.filter(policy_number="POL-NEW-111").first()
        self.assertIsNotNone(policy)
        self.assertEqual(policy.status, "pending")
        self.assertEqual(policy.source, "google_search")
        self.assertEqual(policy.business_type, "renewal")
        self.assertEqual(str(policy.bound_date), "2026-06-04")

    def test_edit_policy_with_new_fields(self):
        policy = InsurancePolicy.objects.create(
            organization=self.org,
            client=Client.objects.create(organization=self.org, first_name="A", last_name="B"),
            insurance_company=self.company,
            policy_number="POL-EDIT-222",
            premium=Decimal("800.00"),
            commission_rate=Decimal("15.00"),
            start_date="2026-06-01",
            end_date="2026-12-01",
            stage="quote",
            status="active"
        )
        # Edit policy via AJAX POST
        response = self.client.post(reverse("edit-insurance-policy", args=[policy.id]), {
            "insurance_company": self.company.id,
            "client_name": "A B",
            "policy_number": "POL-EDIT-222",
            "premium": "850.00",
            "commission_rate": "15.00",
            "stage": "bound",
            "status": "rejected",
            "insurance_type": "trucking",
            "source": "meta_platform",
            "business_type": "rewrite",
            "bound_date": "2026-06-02",
            "start_date": "2026-06-03",
            "end_date": "2026-12-03",
            "insurance_period_months": "6",
        })
        policy.refresh_from_db()
        self.assertEqual(policy.status, "rejected")
        self.assertEqual(policy.source, "meta_platform")
        self.assertEqual(policy.business_type, "rewrite")
        self.assertEqual(str(policy.bound_date), "2026-06-02")
        self.assertEqual(policy.premium, Decimal("850.00"))

    def test_agent_detail_period_auditing(self):
        # Assign agent role capabilities to user
        membership = OrganizationMembership.objects.filter(user=self.user, organization=self.org).first()
        membership.can_deal_with_insurance = True
        membership.save()

        client = Client.objects.create(organization=self.org, first_name="Audited", last_name="Client")
        # Create policies with different dates
        from django.utils import timezone
        p1 = InsurancePolicy.objects.create(
            organization=self.org,
            client=client,
            insurance_company=self.company,
            policy_number="POL-A",
            premium=Decimal("100.00"),
            commission_rate=Decimal("15.00"),
            start_date="2026-06-01",
            end_date="2026-12-01",
            stage="bound",
            status="active",
            added_by=self.user
        )
        p1.created_at = timezone.now() # today
        p1.save()

        # Request today audit
        response = self.client.get(reverse("insurance-agent-detail", args=[self.user.id]) + "?period=today")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["bound_count"], 1)
        self.assertEqual(response.context["total_premium"], Decimal("100.00"))



class AddVehicleViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="password123")
        self.org = Organization.objects.create(name="Test Org", city="NYC")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True,
            role="owner",
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Doe",
        )
        self.client = TestClient()
        self.client.login(username="owner", password="password123")

    def test_add_vehicle_post_succeeds(self):
        response = self.client.post(
            reverse("add-vehicle", args=[self.client_obj.id]),
            {
                "vehicle_type": "passenger",
                "plate_type": "personal",
                "vin": "1HGCM82633A123456",
                "vehicle_number": "VEH-123456",
                "year": "2003",
                "make": "Honda",
                "model": "Accord",
                "fuel_type": "gas",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Vehicle.objects.filter(client=self.client_obj, vin="1HGCM82633A123456").exists()
        )

    def test_add_vehicle_page_renders(self):
        response = self.client.get(reverse("add-vehicle", args=[self.client_obj.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save Vehicle")
        self.assertContains(response, "clientSideVinLooksValid")
        self.assertContains(response, "isManualVehicleType")

    def test_add_vehicle_post_boat_skips_strict_vin(self):
        response = self.client.post(
            reverse("add-vehicle", args=[self.client_obj.id]),
            {
                "vehicle_type": "boat",
                "plate_type": "personal",
                "vin": "ABC12345",
                "vehicle_number": "VEH-BOAT01",
                "year": "2015",
                "make": "Sea Ray",
                "model": "210",
                "fuel_type": "gas",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Vehicle.objects.filter(client=self.client_obj, vin="ABC12345", vehicle_type="boat").exists()
        )

    def test_check_vin_ajax_skips_decode_for_boat(self):
        response = self.client.get(
            reverse("check-vin"),
            {
                "vin": "ABC12345",
                "org_id": self.org.id,
                "client_id": self.client_obj.id,
                "vehicle_type": "boat",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_valid"])
        self.assertTrue(data["is_manual_type"])
        self.assertNotIn("decoded", data)

    def test_check_vin_ajax_decodes_passenger(self):
        with self.settings(
            CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
        ):
            response = self.client.get(
                reverse("check-vin"),
                {
                    "vin": "1HGCM82633A123456",
                    "org_id": self.org.id,
                    "client_id": self.client_obj.id,
                    "vehicle_type": "passenger",
                },
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_valid"])
        self.assertFalse(data.get("is_manual_type", False))


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

    def test_duplicate_vin_across_different_clients_allowed(self):
        # 1. Create a second client
        client2 = Client.objects.create(
            organization=self.org,
            first_name="Bob",
            last_name="Johnson",
            source="walk-in"
        )
        
        # 2. Create vehicle with same VIN for client 1
        Vehicle.objects.create(
            client=self.client_obj,
            vin="1234567890ABCDEFG",
            year=2020,
            make="Toyota",
            model="Camry"
        )
        
        # 3. Create vehicle with same VIN for client 2 (should succeed)
        v2 = Vehicle.objects.create(
            client=client2,
            vin="1234567890ABCDEFG",
            year=2022,
            make="Toyota",
            model="Rav4"
        )
        self.assertEqual(v2.vin, "1234567890ABCDEFG")



class ReceiptAddressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password123")
        self.org = Organization.objects.create(name="Test Org", city="NYC")
        OrganizationMembership.objects.create(user=self.user, organization=self.org, is_active=True, role="owner")
        
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="John",
            last_name="Doe",
            building_no="123",
            street_address="Main St",
            city="New York",
            state="NY",
            zip_code="10001",
            source="walk-in"
        )
        self.vehicle = Vehicle.objects.create(
            client=self.client_obj,
            vin="VIN1234567890ABCD",
            vehicle_number="VEH-001"
        )
        self.client = TestClient()
        self.client.login(username="testuser", password="password123")

    def test_service_record_auto_populates_client_details_on_save(self):
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration"
        )
        self.assertEqual(record.client_name, "John Doe")
        self.assertEqual(record.client_address, "123, Main St, New York, NY, 10001")
        self.assertEqual(record.vehicle_number, "VEH-001")
        self.assertEqual(record.vin, "VIN1234567890ABCD")

    def test_client_save_updates_associated_service_records(self):
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration"
        )
        # Verify initial values
        self.assertEqual(record.client_address, "123, Main St, New York, NY, 10001")
        
        # Modify client address and save client
        self.client_obj.building_no = "456"
        self.client_obj.street_address = "Broadway"
        self.client_obj.save()
        
        # Refresh service record from DB and verify values updated
        record.refresh_from_db()
        self.assertEqual(record.client_address, "456, Broadway, New York, NY, 10001")

    def test_pdf_receipt_renders_with_fallback(self):
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration"
        )
        # Clear the snapshot address to force fallback
        record.client_address = ""
        record.save()
        
        response = self.client.get(reverse("service-receipt-pdf", args=[record.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_pdf_receipt_uses_psbc_license_and_keeps_receipt_number_box(self):
        from io import BytesIO
        from pypdf import PdfReader

        self.org.psbc_license = "PSB-LIC-98765"
        self.org.save()
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
        )
        receipt_parts = str(record.receipt_number).split("-")
        receipt_short = receipt_parts[1][-6:] if len(receipt_parts) > 1 else str(record.receipt_number)[:6]

        response = self.client.get(reverse("service-receipt-pdf", args=[record.id]))
        self.assertEqual(response.status_code, 200)

        pdf_text = "".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages
        )
        self.assertIn("PSB-LIC-98765", pdf_text)
        self.assertIn(receipt_short, pdf_text)


class AgentAuditingTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", city="NYC")
        self.space = Space.objects.create(organization=self.org, label="Insurance Space", key="insurance")
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Geico")
        
        # User 1: Deal with insurance
        self.user1 = User.objects.create_user(username="agent1", password="password123")
        self.m1 = OrganizationMembership.objects.create(
            user=self.user1, organization=self.org, is_active=True, role="agent",
            can_deal_with_insurance=True, can_view_spaces=True
        )
        self.m1.accessible_spaces.add(self.space)
        
        # User 2: Deal with insurance
        self.user2 = User.objects.create_user(username="agent2", password="password123")
        self.m2 = OrganizationMembership.objects.create(
            user=self.user2, organization=self.org, is_active=True, role="agent",
            can_deal_with_insurance=True, can_view_spaces=True
        )
        self.m2.accessible_spaces.add(self.space)
        
        # User 3: Do NOT deal with insurance
        self.user3 = User.objects.create_user(username="agent3", password="password123")
        self.m3 = OrganizationMembership.objects.create(
            user=self.user3, organization=self.org, is_active=True, role="agent",
            can_deal_with_insurance=False, can_view_spaces=True
        )
        self.m3.accessible_spaces.add(self.space)

        # Clients
        self.client_obj1 = Client.objects.create(organization=self.org, first_name="Client", last_name="One")
        self.client_obj2 = Client.objects.create(organization=self.org, first_name="Client", last_name="Two")
        
        self.client = TestClient()
        self.client.login(username="agent1", password="password123")

    def test_auditing_metrics_calculation(self):
        # Create some policies/quotes
        # Agent 1 has:
        # - 1 quote
        # - 1 bound policy (premium 1000.00, broker_fee 50.00, commission_rate 10%)
        InsurancePolicy.objects.create(
            organization=self.org, client=self.client_obj1, policy_number="POL-A1",
            insurance_company=self.company, premium=Decimal("500.00"), broker_fee=Decimal("10.00"),
            commission_rate=Decimal("10.00"), stage="quote", status="active", added_by=self.user1,
            start_date="2026-06-01", end_date="2026-12-01", insurance_period_months=6
        )
        InsurancePolicy.objects.create(
            organization=self.org, client=self.client_obj1, policy_number="POL-A2",
            insurance_company=self.company, premium=Decimal("1000.00"), broker_fee=Decimal("50.00"),
            commission_rate=Decimal("10.00"), stage="bound", status="active", added_by=self.user1,
            start_date="2026-06-01", end_date="2026-12-01", insurance_period_months=6
        )
        
        # Agent 2 has:
        # - 1 bound policy (premium 2000.00, broker_fee 100.00, commission_rate 15%)
        InsurancePolicy.objects.create(
            organization=self.org, client=self.client_obj2, policy_number="POL-B1",
            insurance_company=self.company, premium=Decimal("2000.00"), broker_fee=Decimal("100.00"),
            commission_rate=Decimal("15.00"), stage="bound", status="active", added_by=self.user2,
            start_date="2026-06-01", end_date="2026-12-01", insurance_period_months=6
        )
        
        # Access the inventory-detail view for the insurance space
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        
        # Verify only agents who can deal with insurance are in the list
        insurance_agents = response.context["insurance_agents"]
        self.assertEqual(len(insurance_agents), 2)
        agent_ids = [m.user.id for m in insurance_agents]
        self.assertIn(self.user1.id, agent_ids)
        self.assertIn(self.user2.id, agent_ids)
        self.assertNotIn(self.user3.id, agent_ids)
        
        # Verify stats calculations
        agent_stats = response.context["agent_stats"]
        self.assertEqual(len(agent_stats), 2)
        
        # Since agent_stats is sorted by premium volume descending:
        # agent2: total_premium=2000.00, total_profit=400.00 (commission 300.00 + fee 100.00 = 400.00)
        # agent1: total_premium=1000.00, total_profit=150.00 (commission 100.00 + fee 50.00 = 150.00)
        
        stats2 = agent_stats[0]
        self.assertEqual(stats2["agent"], self.user2)
        self.assertEqual(stats2["quotes_count"], 0)
        self.assertEqual(stats2["policies_bound"], 1)
        self.assertEqual(stats2["total_premium"], Decimal("2000.00"))
        self.assertEqual(stats2["total_commission"], Decimal("300.00"))
        self.assertEqual(stats2["total_broker_fee"], Decimal("100.00"))
        self.assertEqual(stats2["total_profit"], Decimal("400.00"))
        
        stats1 = agent_stats[1]
        self.assertEqual(stats1["agent"], self.user1)
        self.assertEqual(stats1["quotes_count"], 1)
        self.assertEqual(stats1["policies_bound"], 1)
        self.assertEqual(stats1["total_premium"], Decimal("1000.00"))
        self.assertEqual(stats1["total_commission"], Decimal("100.00"))
        self.assertEqual(stats1["total_broker_fee"], Decimal("50.00"))
        self.assertEqual(stats1["total_profit"], Decimal("150.00"))
        
        # Verify best performer
        self.assertEqual(response.context["best_performer"]["agent"], self.user2)

    def test_advanced_filters(self):
        # Create different policies to test filter parameters
        # Policy A
        InsurancePolicy.objects.create(
            organization=self.org, client=self.client_obj1, policy_number="POL-FILTER-A",
            insurance_company=self.company, premium=Decimal("1500.00"), broker_fee=Decimal("50.00"),
            commission_rate=Decimal("10.00"), stage="bound", status="active", added_by=self.user1,
            start_date="2026-06-01", end_date="2026-12-01", insurance_period_months=6
        )
        # Policy B
        InsurancePolicy.objects.create(
            organization=self.org, client=self.client_obj2, policy_number="POL-FILTER-B",
            insurance_company=self.company, premium=Decimal("2500.00"), broker_fee=Decimal("80.00"),
            commission_rate=Decimal("12.00"), stage="quote", status="active", added_by=self.user2,
            start_date="2026-06-15", end_date="2026-12-15", insurance_period_months=6
        )
        
        # Filter by stage = "bound"
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]) + "?stage=bound")
        self.assertEqual(len(response.context["policies"]), 1)
        self.assertEqual(response.context["policies"][0].policy_number, "POL-FILTER-A")
        
        # Filter by agent
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]) + f"?agent={self.user2.id}")
        self.assertEqual(len(response.context["policies"]), 1)
        self.assertEqual(response.context["policies"][0].policy_number, "POL-FILTER-B")

        # Filter by min_premium & max_premium
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]) + "?min_premium=2000")
        self.assertEqual(len(response.context["policies"]), 1)
        self.assertEqual(response.context["policies"][0].policy_number, "POL-FILTER-B")

    def test_unearned_commission_deducted_by_transactions(self):
        # Set active_org_id in session for PDF report endpoint compatibility
        session = self.client.session
        session['active_org_id'] = self.org.id
        session.save()

        # Create an inactive policy that has unearned commission
        policy = InsurancePolicy.objects.create(
            organization=self.org, client=self.client_obj1, policy_number="POL-UNEARNED",
            insurance_company=self.company, premium=Decimal("1000.00"), broker_fee=Decimal("0.00"),
            commission_rate=Decimal("10.00"), stage="bound", status="inactive", added_by=self.user1,
            start_date="2026-06-01", end_date="2026-12-01", insurance_period_months=6,
            inactive_date="2026-06-01"
        )
        # Verify initial unearned commission is exactly commission_amount ($100.00)
        self.assertEqual(policy.commission_amount, Decimal("100.00"))
        self.assertEqual(policy.unearned_commission, Decimal("100.00"))

        # Access view and check initial unearned values
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_unearned_commission"], Decimal("100.00"))
        
        # Verify policy unearned in context policies list
        context_policy = next(p for p in response.context["policies"] if p.id == policy.id)
        self.assertEqual(context_policy.unearned_commission, Decimal("100.00"))

        # Create a bank account
        from .models import BankAccount, BankTransaction
        bank_account = BankAccount.objects.create(
            organization=self.org, account_name="Main Account", bank_name="Chase", balance=Decimal("1000.00")
        )

        # Log an income transaction (refund) linked to the company
        tx1 = BankTransaction.objects.create(
            bank_account=bank_account,
            transaction_type=BankTransaction.TransactionType.INCOME,
            amount=Decimal("40.00"),
            category="Commission Refund",
            insurance_company=self.company
        )

        # Access view and check if unearned commission has decreased by $40
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.context["total_unearned_commission"], Decimal("60.00"))
        context_policy = next(p for p in response.context["policies"] if p.id == policy.id)
        self.assertEqual(context_policy.unearned_commission, Decimal("60.00"))

        # Log an expense transaction (another payback/refund) linked to the company
        tx2 = BankTransaction.objects.create(
            bank_account=bank_account,
            transaction_type=BankTransaction.TransactionType.EXPENSE,
            amount=Decimal("80.00"),
            category="Commission Refund",
            insurance_company=self.company
        )

        # Access view and check if unearned commission is now $0.00 (since 40 + 80 = 120 > 100)
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.context["total_unearned_commission"], Decimal("0.00"))
        context_policy = next(p for p in response.context["policies"] if p.id == policy.id)
        self.assertEqual(context_policy.unearned_commission, Decimal("0.00"))

        # Verify company summaries unearned commission
        company_summary = next(c for c in response.context["company_summaries"] if c["id"] == self.company.id)
        self.assertEqual(company_summary["unearned_commission"], Decimal("0.00"))

        # Verify PDF report matches
        response_pdf = self.client.get(reverse("export-insurance-report-pdf"))
        self.assertEqual(response_pdf.status_code, 200)


class CompanyProfileCommissionTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", city="NYC")
        self.owner = User.objects.create_user(username="owner", password="password123")
        self.owner_membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
            can_deal_with_insurance=True,
            can_view_commission=True,
        )
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Geico")
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="John",
            last_name="Doe",
        )
        self.policy = InsurancePolicy.objects.create(
            organization=self.org,
            client=self.client_obj,
            policy_number="POL-RCV",
            insurance_company=self.company,
            premium=Decimal("1000.00"),
            broker_fee=Decimal("0.00"),
            commission_rate=Decimal("10.00"),
            stage="bound",
            status="active",
            added_by=self.owner,
            start_date="2026-06-01",
            end_date="2026-12-01",
            insurance_period_months=6,
        )
        self.client = TestClient()
        self.client.login(username="owner", password="password123")

    def test_bank_transaction_does_not_affect_received_commission(self):
        from .models import BankAccount, BankTransaction

        bank_account = BankAccount.objects.create(
            organization=self.org,
            account_name="Main",
            bank_name="Chase",
            balance=Decimal("1000.00"),
        )
        BankTransaction.objects.create(
            bank_account=bank_account,
            transaction_type=BankTransaction.TransactionType.INCOME,
            amount=Decimal("50.00"),
            category="Commission Payment",
            insurance_company=self.company,
        )
        response = self.client.get(reverse("insurance-company-detail", args=[self.company.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_received_commission"], Decimal("0.00"))

    def test_policy_checkbox_updates_received_commission(self):
        response = self.client.get(reverse("insurance-company-detail", args=[self.company.id]))
        self.assertEqual(response.context["total_received_commission"], Decimal("0.00"))
        self.assertEqual(response.context["total_commission"], Decimal("100.00"))

        response = self.client.post(
            reverse("toggle-policy-commission-received", args=[self.policy.id]),
            {"received": "1"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["received_commission"], "100.00")
        self.assertEqual(data["earned_commission"], "0.00")

        self.policy.refresh_from_db()
        self.assertTrue(self.policy.commission_received)

        response = self.client.get(reverse("insurance-company-detail", args=[self.company.id]))
        self.assertEqual(response.context["total_received_commission"], Decimal("100.00"))
        self.assertEqual(response.context["total_commission"], Decimal("0.00"))

    def test_toggle_denied_without_view_commission_permission(self):
        self.owner_membership.can_view_commission = False
        self.owner_membership.save(update_fields=["can_view_commission"])

        response = self.client.get(reverse("insurance-company-detail", args=[self.company.id]))
        self.assertFalse(response.context["can_manage_commission"])

        response = self.client.post(
            reverse("toggle-policy-commission-received", args=[self.policy.id]),
            {"received": "1"},
        )
        self.assertEqual(response.status_code, 403)


class SplitPaymentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password123")
        self.org = Organization.objects.create(name="Test Org", city="NYC")
        OrganizationMembership.objects.create(user=self.user, organization=self.org, is_active=True, role="owner")
        
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="John",
            last_name="Doe",
            source="walk-in"
        )
        self.vehicle = Vehicle.objects.create(
            client=self.client_obj,
            vin="VIN1234567890ABCD",
            vehicle_number="VEH-001"
        )
        self.client = TestClient()
        self.client.login(username="testuser", password="password123")

    def test_start_process_empty_paid_amount_2_coerced_to_zero(self):
        post_data = {
            "transaction_date": "2026-06-04",
            "service_type": "vehicle_registration",
            "status": "pending",
            "payment_method": "cash",
            "payment_method_2": "",
            "paid_amount_2": "",
            "terminal_number": "123",
            "transaction_type": "OLRS",
            "processing_fee": "100.00",
            "dmv_fee": "50.00",
            "sales_tax": "10.00",
            "dmv_sales_tax": "5.00",
            "credit_card_fee": "0.00",
            "other_fees": "0.00",
            "other_dmv_fee": "0.00",
            "paid_amount": "165.00",
            "referral_balance": "0.00",
            "notes": "Testing blank paid_amount_2"
        }
        response = self.client.post(reverse("start-process", args=[self.vehicle.id]), post_data)
        self.assertEqual(response.status_code, 302)
        
        record = ServiceRecord.objects.filter(vehicle=self.vehicle).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.paid_amount_2, Decimal("0.00"))

    def test_edit_service_empty_paid_amount_2_coerced_to_zero(self):
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            payment_method="cash",
            paid_amount=Decimal("100.00"),
            paid_amount_2=Decimal("50.00"),
            payment_method_2="cash"
        )
        post_data = {
            "transaction_date": "2026-06-04",
            "service_type": "vehicle_registration",
            "status": "pending",
            "payment_method": "cash",
            "payment_method_2": "",
            "paid_amount_2": "",
            "terminal_number": "123",
            "transaction_type": "OLRS",
            "processing_fee": "100.00",
            "dmv_fee": "50.00",
            "sales_tax": "10.00",
            "dmv_sales_tax": "5.00",
            "credit_card_fee": "0.00",
            "other_fees": "0.00",
            "other_dmv_fee": "0.00",
            "paid_amount": "165.00",
            "referral_balance": "0.00",
            "notes": "Testing blank paid_amount_2 in edit"
        }
        response = self.client.post(reverse("edit-service", args=[record.id]), post_data)
        self.assertEqual(response.status_code, 302)
        
        record.refresh_from_db()
        self.assertEqual(record.paid_amount_2, Decimal("0.00"))
        self.assertIsNone(record.payment_method_2)

    def test_edit_service_calculates_paid_amount_1_correctly(self):
        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            payment_method="visa",
            paid_amount=Decimal("153.50"),
            paid_amount_2=Decimal("50.00"),
            payment_method_2="cash"
        )
        response = self.client.get(reverse("edit-service", args=[record.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("service_paid_amount_1", response.context)
        self.assertEqual(response.context["service_paid_amount_1"], Decimal("100.00"))
        self.assertIn("service_paid_amount_2", response.context)
        self.assertEqual(response.context["service_paid_amount_2"], Decimal("50.00"))


class NewsPermissionTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", city="NYC")
        self.owner = User.objects.create_user(username="owner", password="password123")
        self.agent = User.objects.create_user(username="agent", password="password123")
        
        # Owner membership
        OrganizationMembership.objects.create(user=self.owner, organization=self.org, is_active=True, role="owner")
        # Agent membership
        self.membership = OrganizationMembership.objects.create(user=self.agent, organization=self.org, is_active=True, role="member")
        
        self.client = TestClient()

    def test_owner_can_manage_news(self):
        self.client.login(username="owner", password="password123")
        response = self.client.get(reverse("site-news-list"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_manage"])

    def test_agent_cannot_manage_news_by_default(self):
        self.client.login(username="agent", password="password123")
        response = self.client.get(reverse("site-news-list"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_manage"])

    def test_agent_can_manage_news_when_permitted(self):
        self.membership.can_manage_news = True
        self.membership.save()
        self.client.login(username="agent", password="password123")
        response = self.client.get(reverse("site-news-list"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_manage"])

    def test_agent_post_news_permitted(self):
        self.membership.can_manage_news = True
        self.membership.save()
        self.client.login(username="agent", password="password123")
        response = self.client.post(reverse("site-news-list"), {
            "title": "Agent Announcement",
            "content": "Announcement content here",
            "is_active": "on"
        })
        self.assertEqual(response.status_code, 302)
        
        from core.models import SiteNews
        self.assertTrue(SiteNews.objects.filter(title="Agent Announcement").exists())

    def test_owner_can_edit_news(self):
        from core.models import SiteNews
        news = SiteNews.objects.create(
            title="Original Title",
            content="Original content",
            is_active=True,
        )
        self.client.login(username="owner", password="password123")
        response = self.client.post(reverse("site-news-list"), {
            "action": "edit",
            "news_id": news.id,
            "title": "Updated Title",
            "content": "Updated content",
        })
        self.assertEqual(response.status_code, 302)
        news.refresh_from_db()
        self.assertEqual(news.title, "Updated Title")
        self.assertEqual(news.content, "Updated content")
        self.assertFalse(news.is_active)


class KnowledgeHubTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", city="NYC")
        self.owner = User.objects.create_user(username="owner", password="password123")
        self.agent = User.objects.create_user(username="agent", password="password123")
        
        self.owner_membership = OrganizationMembership.objects.create(
            user=self.owner, organization=self.org, is_active=True, role="owner"
        )
        self.agent_membership = OrganizationMembership.objects.create(
            user=self.agent, organization=self.org, is_active=True, role="member"
        )
        
        self.client = TestClient()

    def test_spaces_home_auto_creates_knowledge_hub(self):
        self.owner_membership.can_view_spaces = True
        self.owner_membership.save()
        self.client.login(username="owner", password="password123")
        response = self.client.get(reverse("spaces-home"))
        self.assertEqual(response.status_code, 200)
        
        from core.models import Space
        self.assertTrue(Space.objects.filter(organization=self.org, key="knowledge_hub").exists())

    def test_agent_cannot_view_knowledge_hub_without_accessible_spaces(self):
        self.client.login(username="agent", password="password123")
        # trigger auto-creation first
        from core.models import Space
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        
        response = self.client.get(reverse("inventory-detail", args=[space.id]))
        self.assertEqual(response.status_code, 403)

    def test_agent_can_view_knowledge_hub_with_accessible_spaces(self):
        self.agent_membership.can_view_spaces = True
        self.agent_membership.save()
        self.client.login(username="agent", password="password123")
        # trigger auto-creation first
        from core.models import Space
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        
        self.agent_membership.accessible_spaces.add(space)
        
        response = self.client.get(reverse("inventory-detail", args=[space.id]))
        self.assertEqual(response.status_code, 200)

    def test_owner_can_add_material(self):
        self.owner_membership.can_view_spaces = True
        self.owner_membership.save()
        self.client.login(username="owner", password="password123")
        from core.models import Space
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        self.owner_membership.accessible_spaces.add(space)
        
        response = self.client.post(reverse("add-knowledge-material", args=[space.id]), {
            "title": "Test Guideline",
            "description": "Step 1 details",
            "step_number": 1,
            "external_url": "https://google.com"
        })
        self.assertEqual(response.status_code, 302)
        
        from core.models import KnowledgeHubMaterial
        self.assertTrue(KnowledgeHubMaterial.objects.filter(title="Test Guideline", step_number=1).exists())

    def test_agent_cannot_add_material(self):
        self.client.login(username="agent", password="password123")
        from core.models import Space
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        
        response = self.client.post(reverse("add-knowledge-material", args=[space.id]), {
            "title": "Hack material",
            "description": "Agent adding material",
            "step_number": 2
        })
        self.assertEqual(response.status_code, 403)

    def test_owner_cannot_view_spaces_without_permission(self):
        self.client.login(username="owner", password="password123")
        response = self.client.get(reverse("spaces-home"))
        self.assertEqual(response.status_code, 403)

    def test_owner_cannot_view_space_without_accessible_spaces(self):
        self.owner_membership.can_view_spaces = True
        self.owner_membership.save()
        self.client.login(username="owner", password="password123")
        from core.models import Space
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        response = self.client.get(reverse("inventory-detail", args=[space.id]))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_view_space_with_permissions(self):
        self.owner_membership.can_view_spaces = True
        self.owner_membership.save()
        self.client.login(username="owner", password="password123")
        from core.models import Space
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        self.owner_membership.accessible_spaces.add(space)
        response = self.client.get(reverse("inventory-detail", args=[space.id]))
        self.assertEqual(response.status_code, 200)

    def test_agent_with_permission_can_add_material(self):
        self.agent_membership.can_manage_knowledge_hub = True
        self.agent_membership.can_view_spaces = True
        self.agent_membership.save()
        
        self.client.login(username="agent", password="password123")
        from core.models import Space
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        self.agent_membership.accessible_spaces.add(space)
        
        response = self.client.post(reverse("add-knowledge-material", args=[space.id]), {
            "title": "Allowed Material",
            "description": "Agent adding material with permission",
            "step_number": 2
        })
        self.assertEqual(response.status_code, 302)
        
        from core.models import KnowledgeHubMaterial
        self.assertTrue(KnowledgeHubMaterial.objects.filter(title="Allowed Material", step_number=2).exists())

    def test_agent_with_permission_but_without_space_access_cannot_add_material(self):
        self.agent_membership.can_manage_knowledge_hub = True
        self.agent_membership.save()
        
        self.client.login(username="agent", password="password123")
        from core.models import Space
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        
        response = self.client.post(reverse("add-knowledge-material", args=[space.id]), {
            "title": "Hack Material",
            "description": "Agent adding material without space access",
            "step_number": 2
        })
        self.assertEqual(response.status_code, 403)

    def test_agent_without_permission_cannot_delete_material(self):
        from core.models import Space, KnowledgeHubMaterial
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        material = KnowledgeHubMaterial.objects.create(space=space, title="Delete Me Agent", step_number=1)
        
        self.client.login(username="agent", password="password123")
        response = self.client.post(reverse("delete-knowledge-material", args=[material.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(KnowledgeHubMaterial.objects.filter(id=material.id).exists())

    def test_agent_with_permission_can_delete_material(self):
        self.agent_membership.can_manage_knowledge_hub = True
        self.agent_membership.save()
        
        from core.models import Space, KnowledgeHubMaterial
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        self.agent_membership.accessible_spaces.add(space)
        material = KnowledgeHubMaterial.objects.create(space=space, title="Delete Me Agent 2", step_number=1)
        
        self.client.login(username="agent", password="password123")
        response = self.client.post(reverse("delete-knowledge-material", args=[material.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(KnowledgeHubMaterial.objects.filter(id=material.id).exists())

    def test_agent_with_permission_but_without_space_access_cannot_delete_material(self):
        self.agent_membership.can_manage_knowledge_hub = True
        self.agent_membership.save()
        
        from core.models import Space, KnowledgeHubMaterial
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        material = KnowledgeHubMaterial.objects.create(space=space, title="Delete Me Agent 3", step_number=1)
        
        self.client.login(username="agent", password="password123")
        response = self.client.post(reverse("delete-knowledge-material", args=[material.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(KnowledgeHubMaterial.objects.filter(id=material.id).exists())

    def test_owner_can_delete_material(self):
        from core.models import Space, KnowledgeHubMaterial
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        material = KnowledgeHubMaterial.objects.create(space=space, title="Delete Me", step_number=1)
        
        self.client.login(username="owner", password="password123")
        response = self.client.post(reverse("delete-knowledge-material", args=[material.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(KnowledgeHubMaterial.objects.filter(id=material.id).exists())

    def test_toggle_agent_knowledge_hub_permission(self):
        self.client.login(username="owner", password="password123")
        
        response = self.client.post(reverse("update-agent-permissions"), {
            "membership_id": self.agent_membership.id,
            "field": "can_manage_knowledge_hub",
            "value": "true"
        })
        self.assertEqual(response.status_code, 200)
        self.agent_membership.refresh_from_db()
        self.assertTrue(self.agent_membership.can_manage_knowledge_hub)

        # toggle off
        response = self.client.post(reverse("update-agent-permissions"), {
            "membership_id": self.agent_membership.id,
            "field": "can_manage_knowledge_hub",
            "value": "false"
        })
        self.assertEqual(response.status_code, 200)
        self.agent_membership.refresh_from_db()
        self.assertFalse(self.agent_membership.can_manage_knowledge_hub)


class ClientIntakeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="password123")
        self.org = Organization.objects.create(name="Test Org", city="NYC", portal_token="test-portal-token", is_active=True)
        OrganizationMembership.objects.create(user=self.user, organization=self.org, is_active=True, role="owner")
        self.client = TestClient()

    def test_public_intake_form_contains_source_dropdown(self):
        response = self.client.get(reverse("public-intake-direct", args=[self.org.portal_token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="source"')
        self.assertContains(response, 'value="google_search" selected')

    def test_public_intake_submission_saves_source(self):
        from core.models import ClientIntake, Referral
        dealer = Referral.objects.create(organization=self.org, name="Portal Dealer", category="dealer")
        response = self.client.post(reverse("public-intake-direct", args=[self.org.portal_token]), {
            "first_name": "Intake",
            "last_name": "Test",
            "gender": "male",
            "phone_number": "1234567890",
            "vin": "12345678901234567",
            "source": "dealer",
            "referral_select": str(dealer.id),
            "services": ["registration_title"],
            "vehicle_type": "passenger",
            "fuel_type": "gas",
        })
        # Check redirect to success page
        self.assertEqual(response.status_code, 302)
        # Verify intake object is created and has correct source
        intake = ClientIntake.objects.filter(organization=self.org).first()
        self.assertIsNotNone(intake)
        self.assertEqual(intake.source, "dealer")

    def test_approve_intake_propagates_source_to_client(self):
        from core.models import ClientIntake
        intake = ClientIntake.objects.create(
            organization=self.org,
            first_name="Intake",
            last_name="Test",
            gender="male",
            phone_number="1234567890",
            vin="12345678901234567",
            source="meta_platform",
        )
        self.client.login(username="owner", password="password123")
        response = self.client.get(reverse("approve-intake", args=[intake.id]))
        self.assertEqual(response.status_code, 302) # Redirects to dashboard
        
        # Verify client was created with the correct source
        client = Client.objects.filter(organization=self.org, first_name="Intake").first()
        self.assertIsNotNone(client)
        self.assertEqual(client.source, "meta_platform")

    def test_intake_rejects_non_pdf_insurance_id_card(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        pdf = SimpleUploadedFile("id.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        jpg = SimpleUploadedFile("id.jpg", b"fakejpg", content_type="image/jpeg")
        base = {
            "first_name": "Intake",
            "last_name": "Test",
            "gender": "male",
            "phone_number": "1234567890",
            "vin": "12345678901234567",
            "source": "walk_in",
            "services": ["registration_title"],
            "vehicle_type": "passenger",
            "fuel_type": "gas",
        }
        ok = self.client.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            {**base, "insurance_id_card": pdf},
        )
        self.assertEqual(ok.status_code, 302)
        bad = self.client.post(
            reverse("public-intake-direct", args=[self.org.portal_token]),
            {**base, "insurance_id_card": jpg},
        )
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, "Insurance ID card must be a PDF file.")

    def test_approve_intake_copies_insurance_id_to_client_documents(self):
        from core.models import ClientIntake, ServiceDocument
        from django.core.files.uploadedfile import SimpleUploadedFile

        pdf = SimpleUploadedFile("insurance-card.pdf", b"%PDF-1.4 insurance", content_type="application/pdf")
        intake = ClientIntake.objects.create(
            organization=self.org,
            first_name="Doc",
            last_name="Upload",
            gender="male",
            phone_number="1234567890",
            vin="VIN12345678901234",
            source="referral",
        )
        intake.insurance_id_card.save("insurance-card.pdf", pdf, save=True)
        self.client.login(username="owner", password="password123")
        response = self.client.get(reverse("approve-intake", args=[intake.id]))
        self.assertEqual(response.status_code, 302)
        client = Client.objects.filter(organization=self.org, first_name="Doc").first()
        self.assertIsNotNone(client)
        doc = ServiceDocument.objects.filter(
            vehicle__client=client,
            document_type="insurance_id",
        ).first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.display_name, "Insurance ID Card")


class DocumentsSpaceTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Docs Org", city="NYC")
        self.owner = User.objects.create_user(username="docsowner", password="password123")
        self.owner_membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
            can_view_spaces=True,
            can_manage_documents=True,
        )
        self.space = Space.objects.create(
            organization=self.org,
            key="documents",
            label="Documents",
            description="Document records",
        )
        self.owner_membership.accessible_spaces.add(self.space)
        self.client = TestClient()
        self.client.login(username="docsowner", password="password123")

    def test_spaces_home_creates_documents_space(self):
        response = self.client.get(reverse("spaces-home"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Space.objects.filter(organization=self.org, key="documents").exists())

    def test_documents_space_renders(self):
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Documents")
        self.assertContains(response, "Document Type")

    def test_no_default_document_types_seeded(self):
        from core.models import SpaceDocumentType

        self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(SpaceDocumentType.objects.filter(space=self.space).count(), 0)

    def test_add_folder_and_record(self):
        from core.models import DocumentFolder, SpaceDocumentRecord, SpaceDocumentType

        response = self.client.post(
            reverse("add-document-folder", args=[self.space.id]),
            {"name": "DMV Forms"},
        )
        self.assertEqual(response.status_code, 302)
        folder = DocumentFolder.objects.get(space=self.space, name="DMV Forms")
        doc_type = SpaceDocumentType.objects.create(
            space=self.space,
            organization=self.org,
            name="MV-82",
        )
        response = self.client.post(
            reverse("add-document-record", args=[self.space.id]),
            {
                "folder_id": folder.id,
                "document_type": doc_type.id,
                "order_number": "ORD-100",
                "range_start": "5001",
                "range_end": "5100",
                "quantity": "250",
            },
        )
        self.assertEqual(response.status_code, 302)
        record = SpaceDocumentRecord.objects.get(space=self.space)
        self.assertTrue(record.record_number.startswith("DOC-"))
        self.assertEqual(record.order_number, "ORD-100")
        self.assertEqual(record.range_start, "5001")
        self.assertEqual(record.range_end, "5100")
        self.assertEqual(record.quantity, 250)
        self.assertEqual(record.added_by, self.owner)

    def test_rename_folder_and_document_type(self):
        from core.models import DocumentFolder, SpaceDocumentType

        folder = DocumentFolder.objects.create(
            space=self.space,
            organization=self.org,
            name="Old Folder",
            created_by=self.owner,
        )
        doc_type = SpaceDocumentType.objects.create(
            space=self.space,
            organization=self.org,
            name="Old Type",
        )

        response = self.client.post(
            reverse("edit-document-folder", args=[folder.id]),
            {"name": "New Folder", "redirect_folder_id": folder.id},
        )
        self.assertEqual(response.status_code, 302)
        folder.refresh_from_db()
        self.assertEqual(folder.name, "New Folder")

        response = self.client.post(
            reverse("edit-document-type", args=[doc_type.id]),
            {"name": "New Type", "folder_id": folder.id},
        )
        self.assertEqual(response.status_code, 302)
        doc_type.refresh_from_db()
        self.assertEqual(doc_type.name, "New Type")


class MotorclubTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Motor Org", city="NYC")
        self.owner = User.objects.create_user(username="mcowner", password="password123")
        self.owner_membership = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
            can_view_spaces=True,
        )
        self.space = Space.objects.create(
            organization=self.org,
            key="motorclub",
            label="Motor Club",
            description="Roadside assistance",
        )
        self.owner_membership.accessible_spaces.add(self.space)
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Road",
            last_name="Runner",
        )
        self.client = TestClient()
        self.client.login(username="mcowner", password="password123")

    def test_spaces_home_creates_motorclub_space(self):
        response = self.client.get(reverse("spaces-home"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Space.objects.filter(organization=self.org, key="motorclub").exists())

    def test_motorclub_space_renders(self):
        response = self.client.get(reverse("inventory-detail", args=[self.space.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Motor Club")

    def test_add_membership_and_profit_split(self):
        from core.models import MotorclubConfig, MotorclubMembership
        from core.motorclub_crm import split_profits_for_tier

        config = MotorclubConfig.objects.create(organization=self.org, tier_50_provider_take=Decimal("28.00"))
        provider, psb = split_profits_for_tier(50, config)
        self.assertEqual(provider, Decimal("28.00"))
        self.assertEqual(psb, Decimal("22.00"))

        response = self.client.post(reverse("add-motorclub-membership", args=[self.space.id]), {
            "client_id": self.client_obj.id,
            "tier": "50",
            "channel": "insurance_client",
            "status": "active",
        })
        self.assertEqual(response.status_code, 302)
        membership = MotorclubMembership.objects.get(client=self.client_obj)
        self.assertEqual(membership.tier, 50)
        self.assertTrue(membership.membership_number.startswith("MC-"))

    def test_client_profile_hides_motorclub_without_membership(self):
        response = self.client.get(reverse("client-detail", args=[self.client_obj.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Active Roadside Plan")
        self.assertNotContains(response, "Motor Club history on file")

    def test_client_profile_shows_motorclub_card(self):
        from datetime import date

        from core.models import MotorclubMembership

        MotorclubMembership.objects.create(
            organization=self.org,
            space=self.space,
            client=self.client_obj,
            tier=75,
            channel="direct",
            status="active",
            start_date=date(2026, 1, 15),
            end_date=date(2027, 1, 15),
            provider_profit=Decimal("42.00"),
            psb_profit=Decimal("33.00"),
            added_by=self.owner,
        )
        response = self.client.get(reverse("client-detail", args=[self.client_obj.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Motor Club")
        self.assertContains(response, "cpp-motorclub-icon")
        self.assertContains(response, "$75")
        self.assertContains(response, "Jan 15, 2026")
        self.assertNotContains(response, "PSB profit")

    def test_client_profile_finds_motorclub_via_insurance_policy_link(self):
        from datetime import date

        from core.models import InsuranceCompany, InsurancePolicy, MotorclubMembership

        other_client = Client.objects.create(
            organization=self.org,
            first_name="Road",
            last_name="Runner",
        )
        company = InsuranceCompany.objects.create(organization=self.org, name="Geico")
        policy = InsurancePolicy.objects.create(
            organization=self.org,
            client=self.client_obj,
            policy_number="POL-MC-LINK",
            insurance_company=company,
            premium=Decimal("1000.00"),
            commission_rate=Decimal("10.00"),
            stage="bound",
            status="active",
            added_by=self.owner,
            start_date="2026-05-01",
            end_date="2026-11-01",
        )
        MotorclubMembership.objects.create(
            organization=self.org,
            space=self.space,
            client=other_client,
            insurance_policy=policy,
            tier=50,
            channel="insurance_client",
            status="active",
            start_date=date(2026, 2, 1),
            end_date=date(2027, 2, 1),
            provider_profit=Decimal("28.00"),
            psb_profit=Decimal("22.00"),
            added_by=self.owner,
        )

        response = self.client.get(reverse("client-detail", args=[self.client_obj.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cpp-motorclub-icon")
        self.assertContains(response, "$50")
        self.assertContains(response, "Active Roadside Plan")

    def test_client_profile_finds_motorclub_via_matching_ssn(self):
        from datetime import date

        from core.models import MotorclubMembership

        self.client_obj.ssn = "123-45-6789"
        self.client_obj.save()
        duplicate_client = Client.objects.create(
            organization=self.org,
            first_name="Road",
            last_name="Runner",
            ssn="123-45-6789",
        )
        MotorclubMembership.objects.create(
            organization=self.org,
            space=self.space,
            client=duplicate_client,
            tier=35,
            channel="direct",
            status="active",
            start_date=date(2026, 3, 1),
            end_date=date(2027, 3, 1),
            provider_profit=Decimal("20.00"),
            psb_profit=Decimal("15.00"),
            added_by=self.owner,
        )

        response = self.client.get(reverse("client-detail", args=[self.client_obj.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cpp-motorclub-icon")
        self.assertContains(response, "$35")

    def test_add_membership_from_client_syncs_to_crm(self):
        from core.models import MotorclubMembership

        response = self.client.post(
            reverse("add-motorclub-membership-client", args=[self.client_obj.id]),
            {
                "tier": "35",
                "channel": "direct",
                "status": "active",
                "start_date": "2026-06-01",
                "end_date": "2027-06-01",
            },
        )
        self.assertEqual(response.status_code, 302)
        membership = MotorclubMembership.objects.get(client=self.client_obj)
        self.assertEqual(membership.tier, 35)
        self.assertEqual(str(membership.start_date), "2026-06-01")
        self.assertIn("tab=members", response.url)

        crm_response = self.client.get(reverse("inventory-detail", args=[self.space.id]) + "?tab=members")
        self.assertContains(crm_response, self.client_obj.name)
        self.assertContains(crm_response, "Delete")


class UnearnedCommissionCalculationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", city="NYC")
        self.user = User.objects.create_user(username="agent", password="password123")
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, is_active=True, role="owner",
        )
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Progressive")
        self.client_obj = Client.objects.create(
            organization=self.org, first_name="Jane", last_name="Smith",
        )

    def _create_policy(self, **kwargs):
        defaults = {
            "organization": self.org,
            "client": self.client_obj,
            "policy_number": "POL-UNEARNED-CALC",
            "insurance_company": self.company,
            "premium": Decimal("1000.00"),
            "broker_fee": Decimal("0.00"),
            "commission_rate": Decimal("12.00"),
            "stage": "bound",
            "status": "inactive",
            "added_by": self.user,
            "start_date": "2026-05-01",
            "end_date": "2026-11-01",
            "insurance_period_months": 6,
            "inactive_date": "2026-06-08",
        }
        defaults.update(kwargs)
        return InsurancePolicy.objects.create(**defaults)

    def test_mid_term_cancellation_prorates_unearned(self):
        policy = self._create_policy()
        self.assertEqual(policy.commission_amount, Decimal("120.00"))
        term_days = (policy.end_date - policy.start_date).days
        remaining_days = (policy.end_date - policy.inactive_date).days
        expected = (Decimal("120.00") * Decimal(remaining_days) / Decimal(term_days)).quantize(
            Decimal("0.01")
        )
        self.assertEqual(policy.unearned_commission, expected)
        self.assertLess(policy.unearned_commission, policy.commission_amount)

    def test_longer_end_date_not_capped_by_insurance_period_months(self):
        """Regression: 12-month term with 6-month period must not return full commission."""
        policy = self._create_policy(
            end_date="2027-05-01",
            insurance_period_months=6,
        )
        term_days = (policy.end_date - policy.start_date).days
        remaining_days = (policy.end_date - policy.inactive_date).days
        expected = (Decimal("120.00") * Decimal(remaining_days) / Decimal(term_days)).quantize(
            Decimal("0.01")
        )
        self.assertEqual(policy.unearned_commission, expected)
        self.assertLess(policy.unearned_commission, Decimal("120.00"))

    def test_cancel_on_effective_date_returns_full_commission(self):
        policy = self._create_policy(inactive_date="2026-05-01")
        self.assertEqual(policy.unearned_commission, Decimal("120.00"))

    def test_cancel_before_effective_date_returns_full_commission(self):
        policy = self._create_policy(inactive_date="2026-04-15")
        self.assertEqual(policy.unearned_commission, Decimal("120.00"))

    def test_cancel_on_or_after_expiration_returns_zero(self):
        policy = self._create_policy(inactive_date="2026-11-01")
        self.assertEqual(policy.unearned_commission, Decimal("0.00"))
        policy = self._create_policy(
            policy_number="POL-UNEARNED-LATE",
            inactive_date="2026-12-01",
        )
        self.assertEqual(policy.unearned_commission, Decimal("0.00"))

    def test_inactive_without_cancellation_date_has_zero_unearned(self):
        policy = self._create_policy(inactive_date=None)
        self.assertEqual(policy.unearned_commission, Decimal("0.00"))

    def test_calculate_unearned_commission_unit_cases(self):
        from datetime import date
        from core.insurance_commissions import calculate_unearned_commission

        commission = Decimal("100.00")
        start = date(2026, 5, 1)
        end = date(2026, 11, 1)

        self.assertEqual(
            calculate_unearned_commission(commission, start, end, date(2026, 5, 1)),
            Decimal("100.00"),
        )
        self.assertEqual(
            calculate_unearned_commission(commission, start, end, date(2026, 11, 1)),
            Decimal("0.00"),
        )
        self.assertEqual(
            calculate_unearned_commission(commission, start, end, None),
            Decimal("0.00"),
        )
        self.assertEqual(
            calculate_unearned_commission(Decimal("0"), start, end, date(2026, 6, 1)),
            Decimal("0.00"),
        )

        term_days = (end - start).days
        remaining_days = (end - date(2026, 6, 8)).days
        expected = (commission * Decimal(remaining_days) / Decimal(term_days)).quantize(
            Decimal("0.01")
        )
        self.assertEqual(
            calculate_unearned_commission(commission, start, end, date(2026, 6, 8)),
            expected,
        )


class TransactionDateMetricsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="metricsuser", password="password123")
        self.org = Organization.objects.create(name="Metrics Org", city="NYC")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True,
            role="owner",
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Doe",
        )
        self.vehicle = Vehicle.objects.create(
            client=self.client_obj,
            vin="VINMETRICS1234567",
            vehicle_number="VEH-M1",
        )

    def test_backdated_transaction_counts_on_transaction_date_not_today(self):
        today = date(2026, 6, 8)
        backdate = date(2026, 6, 4)
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_date=backdate,
            processing_fee=Decimal("25.00"),
        )

        scope_qs = ServiceRecord.objects.filter(organization=self.org)
        cards = build_service_cards(scope_qs, [self.org], today, month_start, year_start)
        reg_card = next(c for c in cards if c["key"] == "vehicle_registration")

        self.assertEqual(reg_card["daily_count"], 0)
        self.assertEqual(reg_card["monthly_count"], 1)
        self.assertEqual(reg_card["yearly_count"], 1)
        self.assertEqual(reg_card["total_count"], 1)


class FinanceBiTransactionDateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="financeuser", password="password123")
        self.org = Organization.objects.create(name="Finance Org", city="NYC")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True,
            role="owner",
            can_view_reports=True,
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Pat",
            last_name="Lee",
        )
        self.vehicle = Vehicle.objects.create(
            client=self.client_obj,
            vin="VINFINANCE1234567",
            vehicle_number="VEH-F1",
        )
        self.http = TestClient()
        self.http.login(username="financeuser", password="password123")

    def test_yearly_report_pdf_uses_transaction_date(self):
        today = date(2026, 6, 8)
        backdate = date(2026, 6, 4)
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_date=backdate,
            service_fee=Decimal("100.00"),
            processing_fee=Decimal("25.00"),
        )

        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            from unittest.mock import patch

            with patch("core.views.timezone.localdate", return_value=today):
                response = self.http.get(reverse("yearly-report-pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_custom_range_report_pdf_uses_transaction_date(self):
        backdate = date(2026, 6, 4)
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_date=backdate,
            service_fee=Decimal("80.00"),
            processing_fee=Decimal("20.00"),
        )

        response = self.http.get(
            reverse("custom-pdf"),
            {"from": "2026-06-04", "to": "2026-06-04"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_daily_payment_cards_bucket_cash_by_transaction_date(self):
        tx_date = date(2026, 6, 4)
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_date=tx_date,
            payment_method="cash",
            paid_amount=Decimal("150.00"),
            service_fee=Decimal("150.00"),
        )
        scope = ServiceRecord.objects.filter(organization=self.org)
        cards, total = build_daily_payment_cards(scope, [self.org.id], tx_date)
        cash_card = next(c for c in cards if c["key"] == "cash")
        self.assertEqual(cash_card["total"], Decimal("150.00"))
        self.assertEqual(total, Decimal("150.00"))

    def test_finance_hub_page_loads_successfully(self):
        response = self.http.get(reverse("finance-hub"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Owner's Strategic Audit")

    def test_finance_hub_crm_tab_lists_transactions_with_pagination(self):
        for idx in range(16):
            ServiceRecord.objects.create(
                organization=self.org,
                handled_by=self.user,
                vehicle=self.vehicle,
                service_type="vehicle_registration",
                transaction_date=date(2026, 6, 1 + (idx % 5)),
                service_fee=Decimal("100.00") + idx,
                receipt_number=f"RCPT-CRM-{idx:04d}-{self.org.id}",
            )

        response = self.http.get(reverse("finance-hub"), {"tab": "crm"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Transaction CRM")
        self.assertContains(response, "Showing")
        self.assertContains(response, "16")

        page_two = self.http.get(reverse("finance-hub"), {"tab": "crm", "page": 2})
        self.assertEqual(page_two.status_code, 200)
        self.assertContains(page_two, "Previous")

    def test_finance_hub_crm_filters_by_transaction_date(self):
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_date=date(2026, 5, 10),
            service_fee=Decimal("50.00"),
            receipt_number=f"RCPT-MAY-{self.org.id}",
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="title_only",
            transaction_date=date(2026, 6, 10),
            service_fee=Decimal("75.00"),
            receipt_number=f"RCPT-JUN-{self.org.id}",
        )

        response = self.http.get(
            reverse("finance-hub"),
            {
                "tab": "crm",
                "date_from": "2026-06-01",
                "date_to": "2026-06-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Title Only")
        self.assertContains(response, "2026-06-10")
        self.assertNotContains(response, "RCPT-MAY")

    def test_finance_hub_daily_intake_not_cleared_by_unrelated_date_filters(self):
        tx_date = date(2026, 6, 8)
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_date=tx_date,
            payment_method="cash",
            paid_amount=Decimal("200.00"),
            service_fee=Decimal("200.00"),
        )
        response = self.http.get(
            reverse("finance-hub"),
            {
                "date_from": "2026-01-01",
                "date_to": "2026-06-01",
                "daily_date": tx_date.strftime("%Y-%m-%d"),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "$200.00")

    def test_finance_hub_month_goal_uses_transaction_date_when_filters_applied(self):
        today = date(2026, 6, 8)
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_date=date(2026, 6, 4),
            processing_fee=Decimal("40.00"),
        )
        filtered = ServiceRecord.objects.filter(
            organization=self.org,
            transaction_date__lte=date(2026, 6, 1),
        )
        forecast = build_month_goal_forecast(filtered, today)
        self.assertEqual(forecast["mtd_revenue"], Decimal("0.00"))

        unfiltered = ServiceRecord.objects.filter(organization=self.org)
        forecast_all = build_month_goal_forecast(unfiltered, today)
        self.assertEqual(forecast_all["mtd_revenue"], Decimal("40.00"))


class ClientSearchAjaxTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="searchuser", password="password123")
        self.org = Organization.objects.create(name="Search Org", city="NYC")
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, is_active=True, role="owner"
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="John",
            last_name="Smith",
            middle_name="Michael",
            driver_license="DL123456",
            source="walk-in",
        )
        self.http = TestClient()
        self.http.login(username="searchuser", password="password123")

    def test_dashboard_search_matches_full_name(self):
        response = self.http.get(reverse("client-search-ajax"), {"q": "John Smith"})
        self.assertEqual(response.status_code, 200)
        names = [r["name"] for r in response.json()["results"]]
        self.assertIn("John Michael Smith", names)

    def test_dashboard_search_matches_last_first_format(self):
        response = self.http.get(reverse("client-search-ajax"), {"q": "Smith, John"})
        self.assertEqual(response.status_code, 200)
        names = [r["name"] for r in response.json()["results"]]
        self.assertIn("John Michael Smith", names)

    def test_dashboard_search_matches_first_middle_last(self):
        response = self.http.get(reverse("client-search-ajax"), {"q": "John Michael Smith"})
        self.assertEqual(response.status_code, 200)
        names = [r["name"] for r in response.json()["results"]]
        self.assertIn("John Michael Smith", names)

    def test_dashboard_search_matches_driver_license(self):
        response = self.http.get(reverse("client-search-ajax"), {"q": "DL123456"})
        self.assertEqual(response.status_code, 200)
        names = [r["name"] for r in response.json()["results"]]
        self.assertIn("John Michael Smith", names)

    def test_dashboard_search_matches_first_name_only(self):
        response = self.http.get(reverse("client-search-ajax"), {"q": "John"})
        self.assertEqual(response.status_code, 200)
        names = [r["name"] for r in response.json()["results"]]
        self.assertIn("John Michael Smith", names)

    def test_dashboard_search_matches_last_name_only(self):
        response = self.http.get(reverse("client-search-ajax"), {"q": "Smith"})
        self.assertEqual(response.status_code, 200)
        names = [r["name"] for r in response.json()["results"]]
        self.assertIn("John Michael Smith", names)


class ClientProfileReferralTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="profileuser", password="password123")
        self.org = Organization.objects.create(name="Profile Org", city="NYC")
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, is_active=True, role="owner"
        )
        self.partner = Referral.objects.create(
            organization=self.org, name="Metro Dealer", category="dealer"
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            middle_name="Ann",
            last_name="Doe",
            driver_license="DL999",
            source="dealer",
            referral=self.partner,
            gender="female",
            phone_number="5551234567",
        )
        self.http = TestClient()
        self.http.login(username="profileuser", password="password123")

    def test_client_profile_shows_full_name_and_clickable_referral(self):
        response = self.http.get(reverse("client-detail", args=[self.client_obj.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jane Ann Doe")
        self.assertContains(response, reverse("referral-profile", args=[self.partner.id]))
        self.assertContains(response, "Metro Dealer")

    def test_all_clients_search_by_driver_license(self):
        response = self.http.get(reverse("all-clients"), {"q": "DL999"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jane Ann Doe")

    def test_all_clients_search_by_partial_name(self):
        response = self.http.get(reverse("all-clients"), {"q": "Ann"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jane Ann Doe")

    def test_case_insensitive_duplicate_name_blocked(self):
        Client.objects.create(
            organization=self.org,
            first_name="bob",
            last_name="builder",
            gender="male",
            phone_number="5550000001",
        )
        form = ClientForm(
            {
                "organization": self.org.id,
                "source": "walk-in",
                "first_name": "Bob",
                "last_name": "Builder",
                "gender": "male",
                "phone_number": "5550000002",
                "state": "NY",
            },
            organizations=Organization.objects.filter(id=self.org.id),
        )
        self.assertFalse(form.is_valid())

    def test_case_insensitive_duplicate_referral_name_blocked(self):
        form = ClientForm(
            {
                "organization": self.org.id,
                "source": "dealer",
                "first_name": "New",
                "last_name": "Person",
                "gender": "male",
                "phone_number": "5550000003",
                "state": "NY",
                "referral_select": "new",
                "referral_name": "metro dealer",
                "referral_category": "dealer",
            },
            organizations=Organization.objects.filter(id=self.org.id),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("referral_name", form.errors)

    def test_edit_client_preserves_referral_when_source_unchanged(self):
        form = ClientForm(
            {
                "organization": self.org.id,
                "source": "walk-in",
                "first_name": "Jane",
                "middle_name": "Ann",
                "last_name": "Doe",
                "gender": "female",
                "phone_number": "5551234567",
                "state": "NY",
                "referral_select": "",
            },
            instance=self.client_obj,
            organizations=Organization.objects.filter(id=self.org.id),
        )
        self.assertTrue(form.is_valid())
        client = form.save(commit=False)
        apply_client_referral_from_form(client, form, is_edit=True)
        self.assertEqual(client.referral_id, self.partner.id)

    def test_edit_client_updates_referral_when_selected(self):
        other = Referral.objects.create(
            organization=self.org, name="Other Partner", category="broker"
        )
        form = ClientForm(
            {
                "organization": self.org.id,
                "source": "referral",
                "first_name": "Jane",
                "middle_name": "Ann",
                "last_name": "Doe",
                "gender": "female",
                "phone_number": "5551234567",
                "state": "NY",
                "referral_select": str(other.id),
            },
            instance=self.client_obj,
            organizations=Organization.objects.filter(id=self.org.id),
        )
        self.assertTrue(form.is_valid())
        client = form.save(commit=False)
        apply_client_referral_from_form(client, form, is_edit=True)
        self.assertEqual(client.referral_id, other.id)

    def test_full_display_name_property(self):
        self.assertEqual(self.client_obj.full_display_name, "Jane Ann Doe")

    def test_edit_client_page_shows_saved_referral(self):
        response = self.http.get(reverse("edit-client", args=[self.client_obj.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Metro Dealer")
        self.assertContains(response, 'data-has-referral="true"')
        self.assertContains(response, str(self.partner.id))


class ClientSearchQueryTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Query Org", city="NYC")
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Alpha",
            last_name="Beta",
            middle_name="Gamma",
            driver_license="XYZ789",
        )

    def test_build_full_client_search_q_matches_dl(self):
        qs = Client.objects.filter(build_full_client_search_q("XYZ789"))
        self.assertEqual(qs.count(), 1)

    def test_build_client_name_search_q_matches_single_token(self):
        qs = Client.objects.filter(build_client_name_search_q("Gamma"))
        self.assertEqual(qs.count(), 1)


class ServiceReceiptPaymentHistoryTests(TestCase):
    def setUp(self):
        from io import BytesIO
        from pypdf import PdfReader

        self.PdfReader = PdfReader
        self.BytesIO = BytesIO
        self.user = User.objects.create_user(username="payuser", password="password123")
        self.org = Organization.objects.create(name="Pay Org", city="NYC")
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, is_active=True, role="owner"
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Pay",
            last_name="Client",
            gender="male",
            phone_number="5551112222",
        )
        self.vehicle = Vehicle.objects.create(
            client=self.client_obj,
            vin="1HGBH41JXMN109186",
            vehicle_number="VEH-PAY-001",
        )
        self.http = TestClient()
        self.http.login(username="payuser", password="password123")

    def _pdf_text(self, record):
        response = self.http.get(reverse("service-receipt-pdf", args=[record.id]))
        self.assertEqual(response.status_code, 200)
        return "".join(
            page.extract_text() or ""
            for page in self.PdfReader(self.BytesIO(response.content)).pages
        )

    def test_receipt_hides_payment_history_until_hub_payment(self):
        from core.service_payments import log_balance_payment

        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_type="transmittal",
            processing_fee=Decimal("100.00"),
            paid_amount=Decimal("40.00"),
            payment_method="cash",
        )
        pdf_text = self._pdf_text(record)
        self.assertNotIn("PAYMENT HISTORY", pdf_text)

        log_balance_payment(
            record,
            Decimal("10.00"),
            "cash",
            payment_date="2026-06-15",
            recorded_by=self.user,
            notes="Payment via Outstanding Balances",
        )
        record.paid_amount = Decimal("50.00")
        record.save()
        pdf_text = self._pdf_text(record)
        self.assertIn("PAYMENT HISTORY", pdf_text)
        self.assertIn("Initial payment", pdf_text)

    def test_partial_payment_adds_row_to_receipt(self):
        from core.models import ServiceRecordPayment
        from core.service_payments import log_balance_payment

        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_type="transmittal",
            processing_fee=Decimal("100.00"),
            paid_amount=Decimal("25.00"),
            payment_method="cash",
            transaction_date=date(2026, 6, 2),
        )
        log_balance_payment(
            record,
            Decimal("50.00"),
            "zelle",
            payment_date="2026-06-15",
            recorded_by=self.user,
            notes="Payment via Outstanding Balances",
        )
        record.paid_amount = Decimal("75.00")
        record.save()
        self.assertEqual(ServiceRecordPayment.objects.filter(service_record=record).count(), 2)
        pdf_text = self._pdf_text(record)
        self.assertIn("Jun 02, 2026", pdf_text)
        self.assertIn("Jun 15, 2026", pdf_text)
        self.assertIn("Initial payment", pdf_text)
        self.assertIn("Zelle", pdf_text)
        self.assertIn("Total Paid", pdf_text)

    def test_mark_balance_paid_creates_payment_entry(self):
        from core.models import ServiceRecordPayment

        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_type="transmittal",
            processing_fee=Decimal("80.00"),
            paid_amount=Decimal("0.00"),
        )
        response = self.http.post(
            reverse("mark-balance-paid", args=[record.id]),
            {
                "payment_amount": "30.00",
                "payment_method": "checks",
                "payment_date": "2026-06-20",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        record.refresh_from_db()
        self.assertEqual(record.paid_amount, Decimal("30.00"))
        entry = ServiceRecordPayment.objects.filter(
            service_record=record,
            entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.payment_method, "checks")
        self.assertEqual(entry.amount, Decimal("30.00"))
        self.assertEqual(str(entry.payment_date), "2026-06-20")

    def test_total_paid_not_double_counted_with_opening_and_duplicate_payment(self):
        from core.models import ServiceRecordPayment
        from core.service_payments import (
            compute_ledger_rows,
            log_balance_payment,
            total_paid_for_receipt,
        )

        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_type="transmittal",
            processing_fee=Decimal("430.75"),
            paid_amount=Decimal("200.00"),
            payment_method="cash",
        )
        ServiceRecordPayment.objects.create(
            service_record=record,
            entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
            amount=Decimal("200.00"),
            payment_date=record.transaction_date,
            notes="Initial payment",
        )
        log_balance_payment(
            record,
            Decimal("230.75"),
            "cash",
            recorded_by=self.user,
            notes="Payment via Outstanding Balances",
        )
        record.paid_amount = Decimal("430.75")
        record.save()
        ServiceRecordPayment.objects.create(
            service_record=record,
            entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
            amount=Decimal("200.00"),
            payment_date=record.transaction_date,
            notes="Initial payment",
        )
        self.assertEqual(total_paid_for_receipt(record), Decimal("430.75"))
        rows = compute_ledger_rows(record)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].description, "Initial payment")
        self.assertEqual(rows[0].line_total, Decimal("430.75"))
        self.assertEqual(rows[0].line_paid, Decimal("200.00"))
        self.assertEqual(rows[0].balance_after, Decimal("230.75"))
        self.assertEqual(rows[1].line_paid, Decimal("230.75"))
        self.assertEqual(rows[1].balance_after, Decimal("0.00"))

    def test_running_outstanding_decreases_with_each_payment(self):
        from core.service_payments import compute_ledger_rows, log_balance_payment

        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_type="transmittal",
            processing_fee=Decimal("100.00"),
            paid_amount=Decimal("25.00"),
            transaction_date=date(2026, 6, 2),
        )
        log_balance_payment(
            record,
            Decimal("50.00"),
            "zelle",
            payment_date="2026-06-15",
            recorded_by=self.user,
            notes="Payment via Outstanding Balances",
        )
        record.paid_amount = Decimal("75.00")
        record.save()
        rows = compute_ledger_rows(record)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].balance_after, Decimal("75.00"))
        self.assertEqual(rows[1].balance_after, Decimal("25.00"))

    def test_edit_clears_ledger_without_hub_payments(self):
        from core.service_payments import record_opening_ledger_entry, reset_ledger_after_edit

        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_type="transmittal",
            processing_fee=Decimal("100.00"),
            paid_amount=Decimal("25.00"),
        )
        record_opening_ledger_entry(record, recorded_by=self.user)
        self.assertEqual(record.payment_entries.count(), 1)
        reset_ledger_after_edit(record)
        self.assertEqual(record.payment_entries.count(), 0)

    def test_edit_preserves_ledger_after_hub_payment(self):
        from core.service_payments import log_balance_payment, reset_ledger_after_edit

        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_type="transmittal",
            processing_fee=Decimal("100.00"),
            paid_amount=Decimal("25.00"),
        )
        log_balance_payment(
            record,
            Decimal("10.00"),
            "cash",
            notes="Payment via Outstanding Balances",
            recorded_by=self.user,
        )
        record.paid_amount = Decimal("35.00")
        record.save()
        count_before = record.payment_entries.count()
        reset_ledger_after_edit(record)
        self.assertEqual(record.payment_entries.count(), count_before)

    def test_legacy_initial_payment_row_becomes_opening_with_outstanding(self):
        """Legacy Initial payment rows are converted when the first hub payment is logged."""
        from core.models import ServiceRecordPayment
        from core.service_payments import compute_ledger_rows, log_balance_payment

        record = ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.user,
            vehicle=self.vehicle,
            service_type="vehicle_registration",
            transaction_type="transmittal",
            processing_fee=Decimal("861.50"),
            paid_amount=Decimal("420.50"),
            payment_method="cash",
            transaction_date=date(2026, 6, 2),
        )
        ServiceRecordPayment.objects.create(
            service_record=record,
            entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
            amount=Decimal("420.50"),
            payment_method="cash",
            payment_date=date(2026, 6, 2),
            notes="Initial payment",
        )
        log_balance_payment(
            record,
            Decimal("50.00"),
            "cash",
            payment_date="2026-06-15",
            recorded_by=self.user,
            notes="Payment via Outstanding Balances",
        )
        record.paid_amount = Decimal("470.50")
        record.save()
        rows = compute_ledger_rows(record)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].description, "Initial payment")
        self.assertEqual(rows[0].line_total, Decimal("861.50"))
        self.assertEqual(rows[0].line_paid, Decimal("420.50"))
        self.assertEqual(rows[0].balance_after, Decimal("441.00"))
        self.assertFalse(
            record.payment_entries.filter(
                entry_type=ServiceRecordPayment.ENTRY_PAYMENT,
                notes="Initial payment",
            ).exists()
        )


