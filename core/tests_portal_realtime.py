"""Realtime notifications + actionable quote/task deep-links."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from core.insurance_quote_distribution import assign_lead
from core.insurance_quote_pipeline_models import InsuranceQuoteLead
from core.models import Notification, Organization, OrganizationMembership
from core.notification_actions import is_safe_action_url, task_board_action_url
from core.realtime import user_channel

User = get_user_model()


class NotificationActionUrlTests(TestCase):
    def test_safe_action_url_rules(self):
        self.assertTrue(is_safe_action_url("/dashboard/agent-portal/tasks/?task=1"))
        self.assertFalse(is_safe_action_url("https://evil.example/phish"))
        self.assertFalse(is_safe_action_url("//evil.example/phish"))
        self.assertFalse(is_safe_action_url(""))

    def test_open_notification_uses_action_url(self):
        org = Organization.objects.create(name="RT Org", city="NY", state="NY")
        user = User.objects.create_user(username="rt_agent", password="pass")
        OrganizationMembership.objects.create(
            user=user,
            organization=org,
            role=OrganizationMembership.Role.INSURANCE_AGENT,
            is_active=True,
        )
        notif = Notification.objects.create(
            user=user,
            organization=org,
            event_type="quote_lead_assigned",
            title="New quote lead assigned",
            message="Quote lead: Test",
            action_url="/dashboard/agent-portal/tasks/?task=99",
            level=Notification.Level.INFO,
        )
        client = Client()
        client.login(username="rt_agent", password="pass")
        resp = client.get(reverse("open-notification", args=[notif.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard/agent-portal/tasks/", resp["Location"])
        self.assertIn("task=99", resp["Location"])
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_quote_assign_sets_action_url(self):
        org = Organization.objects.create(name="RT Org 2", city="NY", state="NY")
        owner = User.objects.create_user(username="rt_owner", password="pass")
        agent_user = User.objects.create_user(username="rt_ia", password="pass")
        OrganizationMembership.objects.create(
            user=owner,
            organization=org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        agent = OrganizationMembership.objects.create(
            user=agent_user,
            organization=org,
            role=OrganizationMembership.Role.INSURANCE_AGENT,
            is_active=True,
            can_deal_with_insurance=True,
        )
        lead = InsuranceQuoteLead.objects.create(
            organization=org,
            created_by=owner,
            client_name="Jane Doe",
            phone="555-0100",
            stage=InsuranceQuoteLead.Stage.NEW,
        )
        with self.captureOnCommitCallbacks(execute=True):
            assign_lead(
                lead,
                agent,
                mode=InsuranceQuoteLead.AssignmentMode.MANUAL,
                actor=owner,
            )
        notif = Notification.objects.get(
            user=agent_user, event_type="quote_lead_assigned"
        )
        self.assertTrue(notif.action_url)
        self.assertIn("task=", notif.action_url)
        self.assertTrue(lead.agent_task_id)
        self.assertEqual(
            notif.action_url, task_board_action_url(task_id=lead.agent_task_id)
        )


class PortalRealtimeApiTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="SSE Org", city="NY", state="NY")
        self.user = User.objects.create_user(username="sse_user", password="pass")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client = Client()
        self.client.login(username="sse_user", password="pass")

    def test_notifications_snapshot(self):
        Notification.objects.create(
            user=self.user,
            organization=self.org,
            title="Hello",
            message="World",
            level=Notification.Level.INFO,
            action_url="/dashboard/",
        )
        resp = self.client.get(reverse("portal-notifications-snapshot"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data["unread_count"], 1)
        self.assertTrue(data["notifications"])
        self.assertGreaterEqual(data["newest_id"], 1)

    def test_notifications_snapshot_after_id(self):
        first = Notification.objects.create(
            user=self.user,
            organization=self.org,
            title="Old",
            message="A",
            level=Notification.Level.INFO,
        )
        second = Notification.objects.create(
            user=self.user,
            organization=self.org,
            title="New",
            message="B",
            level=Notification.Level.INFO,
        )
        resp = self.client.get(
            reverse("portal-notifications-snapshot"),
            {"after_id": first.id},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["has_new"])
        ids = [n["id"] for n in data["notifications"]]
        self.assertEqual(ids, [second.id])
        self.assertEqual(data["newest_id"], second.id)

    def test_notifications_wait_returns_existing_immediately(self):
        first = Notification.objects.create(
            user=self.user,
            organization=self.org,
            title="Ready",
            message="Now",
            level=Notification.Level.INFO,
        )
        resp = self.client.get(
            reverse("portal-notifications-wait"),
            {"after_id": first.id - 1, "timeout": 5},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["has_new"])
        self.assertEqual(data["notifications"][0]["id"], first.id)

    def test_events_stream_smoke(self):
        resp = self.client.get(reverse("portal-events-stream"), data={"org": self.org.id})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp["Content-Type"])
        resp.close()

    def test_user_channel_name(self):
        self.assertEqual(user_channel(12), "rm:user:12:events")
