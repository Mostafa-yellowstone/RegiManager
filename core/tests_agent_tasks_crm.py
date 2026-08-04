from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from core.agent_portal_models import AgentTask
from core.agent_portal_services import task_progress_for_membership
from core.models import Organization, OrganizationMembership


class AgentTaskStagesTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="taskowner", password="password123")
        self.agent_user = User.objects.create_user(username="taskagent", password="password123")
        self.org = Organization.objects.create(name="Task Org", city="NYC")
        self.owner_mem = OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
            can_deal_with_insurance=True,
        )
        self.agent_mem = OrganizationMembership.objects.create(
            user=self.agent_user,
            organization=self.org,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
            can_deal_with_insurance=True,
        )
        self.http = Client()

    def test_set_status_syncs_is_done_and_note(self):
        task = AgentTask.objects.create(
            organization=self.org,
            assigned_to=self.agent_mem,
            created_by=self.owner,
            title="Call lead",
        )
        task.set_status(AgentTask.Status.IN_PROGRESS)
        task.refresh_from_db()
        self.assertEqual(task.status, AgentTask.Status.IN_PROGRESS)
        self.assertFalse(task.is_done)

        task.set_status(AgentTask.Status.DONE, note="Reached client and booked quote.")
        task.refresh_from_db()
        self.assertEqual(task.status, AgentTask.Status.DONE)
        self.assertTrue(task.is_done)
        self.assertIsNotNone(task.completed_at)
        self.assertIn("booked quote", task.completion_note)

        task.mark_done(done=False)
        task.refresh_from_db()
        self.assertEqual(task.status, AgentTask.Status.TODO)
        self.assertFalse(task.is_done)
        self.assertIsNone(task.completed_at)

    def test_progress_buckets_by_stage(self):
        AgentTask.objects.create(
            organization=self.org,
            assigned_to=self.agent_mem,
            title="A",
            status=AgentTask.Status.TODO,
        )
        AgentTask.objects.create(
            organization=self.org,
            assigned_to=self.agent_mem,
            title="B",
            status=AgentTask.Status.IN_PROGRESS,
        )
        done = AgentTask.objects.create(
            organization=self.org,
            assigned_to=self.agent_mem,
            title="C",
        )
        done.set_status(AgentTask.Status.DONE, note="Finished.")
        progress = task_progress_for_membership(self.agent_mem)
        self.assertEqual(progress["todo"], 1)
        self.assertEqual(progress["in_progress"], 1)
        self.assertEqual(progress["done"], 1)
        self.assertEqual(progress["open"], 2)
        self.assertEqual(progress["percent"], 33)

    def test_agent_cannot_complete_without_note(self):
        task = AgentTask.objects.create(
            organization=self.org,
            assigned_to=self.agent_mem,
            created_by=self.owner,
            title="Needs note",
        )
        self.http.login(username="taskagent", password="password123")
        response = self.http.post(
            reverse("agent-portal-toggle-task", args=[task.id]),
            {"status": "done"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        task.refresh_from_db()
        self.assertFalse(task.is_done)

        ok = self.http.post(
            reverse("agent-portal-toggle-task", args=[task.id]),
            {"status": "done", "completion_note": "Called and left voicemail."},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(ok.status_code, 200)
        payload = ok.json()
        self.assertTrue(payload["ok"])
        task.refresh_from_db()
        self.assertTrue(task.is_done)
        self.assertEqual(task.status, AgentTask.Status.DONE)

    def test_owner_tasks_crm_access(self):
        AgentTask.objects.create(
            organization=self.org,
            assigned_to=self.agent_mem,
            created_by=self.owner,
            title="CRM visible",
        )
        self.http.login(username="taskowner", password="password123")
        response = self.http.get(reverse("agent-portal-manage-tasks"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tasks CRM")
        self.assertContains(response, "CRM visible")

        self.http.login(username="taskagent", password="password123")
        denied = self.http.get(reverse("agent-portal-manage-tasks"))
        self.assertEqual(denied.status_code, 403)

    def test_owner_create_notifies_agent(self):
        from core.models import Notification

        self.http.login(username="taskowner", password="password123")
        response = self.http.post(
            reverse("agent-portal-create-task"),
            {
                "assigned_to": self.agent_mem.id,
                "title": "Follow up quote",
                "description": "Call today",
                "next": reverse("agent-portal-manage-tasks"),
            },
        )
        self.assertEqual(response.status_code, 302)
        task = AgentTask.objects.get(title="Follow up quote")
        self.assertEqual(task.status, AgentTask.Status.TODO)
        self.assertTrue(
            Notification.objects.filter(
                user=self.agent_user,
                event_type="agent_task_assigned",
                message__icontains="Follow up quote",
            ).exists()
        )
