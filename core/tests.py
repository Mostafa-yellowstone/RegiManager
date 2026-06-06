from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth.models import User
from decimal import Decimal
from core.models import Organization, OrganizationMembership, Client, InsuranceCompany, InsurancePolicy, Space, Vehicle, ServiceRecord

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


class KnowledgeHubTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", city="NYC")
        self.owner = User.objects.create_user(username="owner", password="password123")
        self.agent = User.objects.create_user(username="agent", password="password123")
        
        OrganizationMembership.objects.create(user=self.owner, organization=self.org, is_active=True, role="owner")
        self.agent_membership = OrganizationMembership.objects.create(user=self.agent, organization=self.org, is_active=True, role="member")
        
        self.client = TestClient()

    def test_spaces_home_auto_creates_knowledge_hub(self):
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
        self.client.login(username="agent", password="password123")
        # trigger auto-creation first
        from core.models import Space
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        
        self.agent_membership.accessible_spaces.add(space)
        
        response = self.client.get(reverse("inventory-detail", args=[space.id]))
        self.assertEqual(response.status_code, 200)

    def test_owner_can_add_material(self):
        self.client.login(username="owner", password="password123")
        from core.models import Space
        space, _ = Space.objects.get_or_create(organization=self.org, key="knowledge_hub")
        
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

    def test_agent_with_permission_can_add_material(self):
        self.agent_membership.can_manage_knowledge_hub = True
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
        from core.models import ClientIntake
        # Submit the form
        response = self.client.post(reverse("public-intake-direct", args=[self.org.portal_token]), {
            "first_name": "Intake",
            "last_name": "Test",
            "gender": "male",
            "phone_number": "1234567890",
            "vin": "12345678901234567",
            "source": "referral",
            "services": ["registration_title"],
        })
        # Check redirect to success page
        self.assertEqual(response.status_code, 302)
        # Verify intake object is created and has correct source
        intake = ClientIntake.objects.filter(organization=self.org).first()
        self.assertIsNotNone(intake)
        self.assertEqual(intake.source, "referral")

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




