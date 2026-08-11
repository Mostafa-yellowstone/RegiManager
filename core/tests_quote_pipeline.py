from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.agent_portal_models import AgentAttendanceSession, AgentTask
from core.insurance_quote_distribution import (
    auto_distribute_lead,
    eligible_agents_for_auto,
    is_sunday_ny,
)
from core.insurance_quote_permissions import (
    can_create_quote_leads,
    can_manage_quote_distribution,
    can_receive_quote_distribution,
)
from core.insurance_quote_pipeline_models import (
    InsuranceAgentOffDay,
    InsuranceQuoteLead,
)
from core.models import Organization, OrganizationMembership
from core.role_permissions import apply_role_permission_pack


def _open_attendance(membership, organization, work_date):
    return AgentAttendanceSession.objects.create(
        membership=membership,
        organization=organization,
        work_date=work_date,
        opened_at=timezone.now(),
    )


class QuotePipelineDistributionTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Quote Org", city="NYC")
        self.owner_user = User.objects.create_user(username="qowner", password="password123")
        self.manager_user = User.objects.create_user(username="qmgr", password="password123")
        self.agent_user = User.objects.create_user(username="qagent", password="password123")
        self.agent2_user = User.objects.create_user(username="qagent2", password="password123")

        self.owner = OrganizationMembership.objects.create(
            user=self.owner_user,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        apply_role_permission_pack(self.owner)

        self.manager = OrganizationMembership.objects.create(
            user=self.manager_user,
            organization=self.org,
            role=OrganizationMembership.Role.MANAGER,
            is_active=True,
        )
        apply_role_permission_pack(self.manager)

        self.agent = OrganizationMembership.objects.create(
            user=self.agent_user,
            organization=self.org,
            role=OrganizationMembership.Role.INSURANCE_AGENT,
            is_active=True,
        )
        apply_role_permission_pack(self.agent)

        self.agent2 = OrganizationMembership.objects.create(
            user=self.agent2_user,
            organization=self.org,
            role=OrganizationMembership.Role.INSURANCE_AGENT,
            is_active=True,
        )
        apply_role_permission_pack(self.agent2)

    def test_permissions_create_vs_receive(self):
        self.assertTrue(can_create_quote_leads(self.agent_user, self.org, membership=self.agent))
        self.assertTrue(can_create_quote_leads(self.owner_user, self.org, membership=self.owner))
        self.assertTrue(can_create_quote_leads(self.manager_user, self.org, membership=self.manager))
        self.assertTrue(can_receive_quote_distribution(self.agent))
        self.assertFalse(can_receive_quote_distribution(self.manager))
        self.assertFalse(can_receive_quote_distribution(self.owner))
        self.assertTrue(can_manage_quote_distribution(self.manager_user, self.org, membership=self.manager))
        self.assertFalse(can_manage_quote_distribution(self.agent_user, self.org, membership=self.agent))

    def test_sunday_auto_skips_assignment(self):
        sunday = date(2026, 8, 9)  # known Sunday
        self.assertTrue(is_sunday_ny(sunday))
        lead = InsuranceQuoteLead.objects.create(
            organization=self.org,
            created_by=self.owner_user,
            client_name="Sunday Client",
            phone="5551112222",
            insurance_type="personal_auto",
        )
        _open_attendance(self.agent, self.org, sunday)
        auto_distribute_lead(lead, actor=self.owner_user, work_date=sunday)
        lead.refresh_from_db()
        self.assertIsNone(lead.assigned_to_id)

    def test_off_day_and_absent_excluded(self):
        work = date(2026, 8, 10)  # Monday
        InsuranceAgentOffDay.objects.create(
            organization=self.org,
            membership=self.agent,
            off_date=work,
            reason="PTO",
        )
        # agent2 present
        _open_attendance(self.agent2, self.org, work)
        eligible = eligible_agents_for_auto(self.org, work_date=work)
        ids = {m.id for m in eligible}
        self.assertNotIn(self.agent.id, ids)
        self.assertIn(self.agent2.id, ids)

        lead = InsuranceQuoteLead.objects.create(
            organization=self.org,
            created_by=self.manager_user,
            client_name="Mon Client",
            phone="5553334444",
            insurance_type="commercial_auto",
        )
        auto_distribute_lead(lead, actor=self.manager_user, work_date=work)
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to_id, self.agent2.id)
        self.assertEqual(lead.assignment_mode, InsuranceQuoteLead.AssignmentMode.AUTO)
        self.assertTrue(AgentTask.objects.filter(id=lead.agent_task_id).exists())

    def test_create_lead_endpoint_auto_assigns(self):
        work = date(2026, 8, 11)
        _open_attendance(self.agent, self.org, work)
        self.client.login(username="qmgr", password="password123")
        session = self.client.session
        session["active_org_id"] = self.org.id
        session.save()
        with patch(
            "core.insurance_quote_pipeline_views.auto_distribute_lead"
        ) as mocked:
            # Exercise view path; distribution covered above.
            mocked.side_effect = lambda lead, **kw: lead
            resp = self.client.post(
                reverse("create-quote-lead"),
                {
                    "client_name": "Pat Lee",
                    "phone": "5550009999",
                    "insurance_type": "personal_auto",
                    "has_prior": "on",
                    "notes": "Needs full coverage",
                },
            )
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(
                InsuranceQuoteLead.objects.filter(client_name="Pat Lee").exists()
            )

    def test_old_intake_urls_gone(self):
        from django.urls import NoReverseMatch

        with self.assertRaises(NoReverseMatch):
            reverse("public-insurance-intake-start")
        with self.assertRaises(NoReverseMatch):
            reverse("approve-insurance-intake", args=[1])

    def test_owner_can_edit_and_delete_lead(self):
        lead = InsuranceQuoteLead.objects.create(
            organization=self.org,
            created_by=self.owner_user,
            client_name="Edit Me",
            phone="5551112222",
            stage=InsuranceQuoteLead.Stage.NEW,
        )
        self.client.login(username="qowner", password="password123")
        session = self.client.session
        session["active_org_id"] = self.org.id
        session.save()

        edit = self.client.post(
            reverse("edit-quote-lead", args=[lead.id]),
            {
                "client_name": "Edited Name",
                "phone": "5553334444",
                "email": "e@example.com",
                "insurance_type": "personal_auto",
                "stage": "quoting",
                "notes": "Updated note",
                "has_prior": "on",
            },
        )
        self.assertEqual(edit.status_code, 302)
        lead.refresh_from_db()
        self.assertEqual(lead.client_name, "Edited Name")
        self.assertEqual(lead.phone, "5553334444")
        self.assertEqual(lead.stage, "quoting")
        self.assertTrue(lead.has_prior)

        delete = self.client.post(reverse("delete-quote-lead", args=[lead.id]))
        self.assertEqual(delete.status_code, 302)
        self.assertFalse(InsuranceQuoteLead.objects.filter(id=lead.id).exists())

    def test_agent_cannot_delete_lead(self):
        lead = InsuranceQuoteLead.objects.create(
            organization=self.org,
            created_by=self.owner_user,
            client_name="Protected",
            phone="5550001111",
            assigned_to=self.agent,
            stage=InsuranceQuoteLead.Stage.ASSIGNED,
        )
        self.client.login(username="qagent", password="password123")
        session = self.client.session
        session["active_org_id"] = self.org.id
        session.save()
        resp = self.client.post(reverse("delete-quote-lead", args=[lead.id]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(InsuranceQuoteLead.objects.filter(id=lead.id).exists())
