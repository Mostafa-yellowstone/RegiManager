from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Client,
    Organization,
    OrganizationMembership,
    Referral,
    ServiceRecord,
    Vehicle,
)
from core.referral_metrics import attach_referral_list_metrics
from core.role_permissions import apply_role_permission_pack, pack_for_role


class RolePackTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Role Org", city="NYC")
        self.user = User.objects.create_user(username="roleuser", password="password123")
        self.mem = OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            role=OrganizationMembership.Role.AGENT,
            is_active=True,
        )

    def test_manager_pack_has_reports_not_banking(self):
        pack = pack_for_role(OrganizationMembership.Role.MANAGER)
        self.assertTrue(pack["can_view_reports"])
        self.assertTrue(pack["can_assign_agent_tasks"])
        self.assertFalse(pack["can_view_banking"])
        self.assertFalse(pack["can_deal_with_insurance"])

    def test_accountant_pack_has_banking(self):
        pack = pack_for_role(OrganizationMembership.Role.ACCOUNTANT)
        self.assertTrue(pack["can_view_banking"])
        self.assertTrue(pack["can_manage_referrals"])
        self.assertFalse(pack["can_deal_with_insurance"])

    def test_insurance_agent_pack(self):
        pack = pack_for_role(OrganizationMembership.Role.INSURANCE_AGENT)
        self.assertTrue(pack["can_deal_with_insurance"])
        self.assertFalse(pack["can_view_banking"])

    def test_apply_role_permission_pack(self):
        self.mem.role = OrganizationMembership.Role.MANAGER
        apply_role_permission_pack(self.mem)
        self.mem.refresh_from_db()
        self.assertTrue(self.mem.can_view_reports)
        self.assertFalse(self.mem.can_view_banking)


class PartnerRecordCountTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Partner Org", city="NYC")
        self.owner = User.objects.create_user(username="powner", password="password123")
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.referral = Referral.objects.create(
            organization=self.org,
            name="Partner A",
            is_partner=True,
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="A",
            last_name="B",
            gender="male",
            phone_number="5550001111",
            referral=self.referral,
        )
        self.vehicle = Vehicle.objects.create(
            client=self.client_obj,
            plate_number="ABC1234",
            vin="1HGCM82633A123456",
            year=2020,
            make="Honda",
            model="Civic",
        )
        ServiceRecord.objects.create(
            organization=self.org,
            vehicle=self.vehicle,
            service_type="registration",
            service_fee=Decimal("100.00"),
            processing_fee=Decimal("20.00"),
            handled_by=self.owner,
        )

    def test_via_client_counts_on_list_metrics(self):
        refs = attach_referral_list_metrics([self.referral])
        self.assertEqual(refs[0].record_count, 1)


class ManagerAccountantPortalTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Staff Org", city="NYC")
        self.manager_user = User.objects.create_user(
            username="mgr", password="password123", first_name="Mo", last_name="Manager"
        )
        self.acct_user = User.objects.create_user(
            username="acct", password="password123", first_name="Ann", last_name="Accountant"
        )
        self.manager = OrganizationMembership.objects.create(
            user=self.manager_user,
            organization=self.org,
            role=OrganizationMembership.Role.MANAGER,
            is_active=True,
        )
        apply_role_permission_pack(self.manager)
        self.manager.refresh_from_db()
        self.accountant = OrganizationMembership.objects.create(
            user=self.acct_user,
            organization=self.org,
            role=OrganizationMembership.Role.ACCOUNTANT,
            is_active=True,
        )
        apply_role_permission_pack(self.accountant)
        self.accountant.refresh_from_db()

    def test_manager_lands_on_portal_and_can_add_personal_task(self):
        self.client.login(username="mgr", password="password123")
        home = self.client.get(reverse("agent-portal-home"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Add a personal task")
        self.assertContains(home, "Day audit trail")

        resp = self.client.post(
            reverse("agent-portal-create-task"),
            {
                "assigned_to": str(self.manager.id),
                "title": "Review weekly report",
                "description": "Check finance overview",
            },
        )
        self.assertEqual(resp.status_code, 302)
        from core.agent_portal_models import AgentTask

        self.assertTrue(
            AgentTask.objects.filter(
                organization=self.org,
                assigned_to=self.manager,
                title="Review weekly report",
            ).exists()
        )

    def test_accountant_self_profile_day_filter(self):
        self.client.login(username="acct", password="password123")
        url = reverse("agent-profile", args=[self.accountant.id])
        day = self.client.get(url, {"tab": "day", "activity_date": "2026-07-29"})
        self.assertEqual(day.status_code, 200)
        self.assertContains(day, "Day audit trail")
        workboard = self.client.get(url, {"tab": "workboard"})
        self.assertEqual(workboard.status_code, 200)
        self.assertContains(workboard, "Add a personal task")
