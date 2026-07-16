"""Portal notification mark-as-read behavior."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Notification, Organization, OrganizationMembership

User = get_user_model()


class PortalNotificationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Notif Org", city="NY", state="NY")
        self.user = User.objects.create_user(username="notif_user", password="pass")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.n1 = Notification.objects.create(
            user=self.user,
            organization=self.org,
            event_type="general",
            title="First",
            message="One",
            level=Notification.Level.INFO,
            is_read=False,
        )
        self.n2 = Notification.objects.create(
            user=self.user,
            organization=self.org,
            event_type="general",
            title="Second",
            message="Two",
            level=Notification.Level.WARNING,
            is_read=False,
        )

    def test_open_marks_read(self):
        self.client.login(username="notif_user", password="pass")
        resp = self.client.get(reverse("open-notification", args=[self.n1.id]))
        self.assertEqual(resp.status_code, 302)
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read)

    def test_mark_one_and_mark_all(self):
        self.client.login(username="notif_user", password="pass")
        one = self.client.post(reverse("mark-notification-read", args=[self.n1.id]))
        self.assertEqual(one.status_code, 200)
        data = one.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["unread_count"], 1)
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read)

        all_resp = self.client.post(reverse("mark-all-notifications-read"))
        self.assertEqual(all_resp.status_code, 200)
        self.assertEqual(all_resp.json()["unread_count"], 0)
        self.assertEqual(Notification.objects.filter(user=self.user, is_read=False).count(), 0)
