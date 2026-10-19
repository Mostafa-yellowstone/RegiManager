"""Client notes: editing, change history, done/reopen, notifications, access, and the profile display."""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client as TestClient, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Client, ClientNote, ClientNoteHistory, Notification, Organization, OrganizationMembership


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ClientNoteEditingTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Notes PSB", city="NYC")
        self.owner = User.objects.create_user(username="owner", password="pw-12345", first_name="Olivia", last_name="Owner")
        self.agent = User.objects.create_user(username="agent", password="pw-12345", first_name="Adam", last_name="Agent")
        self.other_agent = User.objects.create_user(username="agent2", password="pw-12345", first_name="Bea")
        OrganizationMembership.objects.create(user=self.owner, organization=self.org, role="owner", is_active=True)
        OrganizationMembership.objects.create(user=self.agent, organization=self.org, role="agent", is_active=True)
        OrganizationMembership.objects.create(user=self.other_agent, organization=self.org, role="agent", is_active=True)
        self.client_obj = Client.objects.create(organization=self.org, first_name="Nora", last_name="Client")
        self.note = ClientNote.objects.create(
            client=self.client_obj,
            created_by=self.owner,
            assigned_to=self.agent,
            content="Call about the title",
            follow_up_date=date(2026, 10, 20),
        )
        self.http = TestClient()
        self.http.force_login(self.owner)

    def _edit(self, **data):
        payload = {
            "content": self.note.content,
            "follow_up_date": self.note.follow_up_date.isoformat() if self.note.follow_up_date else "",
            "assigned_to": str(self.note.assigned_to_id or ""),
        }
        payload.update(data)
        return self.http.post(reverse("edit-client-note", args=[self.note.id]), payload)

    def test_edit_updates_the_note_and_records_every_change(self):
        response = self._edit(content="Call about the title and plates", follow_up_date="2026-10-25", assigned_to=str(self.other_agent.id))
        self.assertRedirects(
            response, f"{reverse('client-detail', args=[self.client_obj.id])}#note-{self.note.id}", fetch_redirect_response=False
        )
        self.note.refresh_from_db()
        self.assertEqual(self.note.content, "Call about the title and plates")
        self.assertEqual(self.note.follow_up_date, date(2026, 10, 25))
        self.assertEqual(self.note.assigned_to, self.other_agent)
        self.assertEqual(self.note.updated_by, self.owner)
        self.assertIsNotNone(self.note.updated_at)

        entry = ClientNoteHistory.objects.get(note=self.note)
        self.assertEqual(entry.action, ClientNoteHistory.Action.EDITED)
        self.assertEqual(entry.actor, self.owner)
        self.assertEqual(
            entry.changes,
            [
                {"field": "Note", "old": "Call about the title", "new": "Call about the title and plates"},
                {"field": "Follow-up date", "old": "Oct 20, 2026", "new": "Oct 25, 2026"},
                {"field": "Assigned to", "old": "Adam Agent", "new": "Bea"},
            ],
        )

    def test_saving_without_changes_adds_no_history(self):
        self._edit()
        self.assertFalse(ClientNoteHistory.objects.exists())
        self.note.refresh_from_db()
        self.assertIsNone(self.note.updated_at)

    def test_clearing_the_follow_up_date_is_recorded(self):
        self._edit(follow_up_date="")
        self.note.refresh_from_db()
        self.assertIsNone(self.note.follow_up_date)
        self.assertEqual(
            ClientNoteHistory.objects.get().changes,
            [{"field": "Follow-up date", "old": "Oct 20, 2026", "new": "No date"}],
        )

    def test_empty_note_or_bad_date_is_rejected(self):
        self._edit(content="   ")
        self._edit(follow_up_date="not-a-date")
        self.note.refresh_from_db()
        self.assertEqual(self.note.content, "Call about the title")
        self.assertFalse(ClientNoteHistory.objects.exists())

    def test_new_assignee_and_follow_up_change_are_notified(self):
        self._edit(follow_up_date="2026-11-01", assigned_to=str(self.other_agent.id))
        assigned = Notification.objects.filter(user=self.other_agent, note=self.note)
        self.assertTrue(assigned.filter(title="Client note assigned to you").exists())
        self.assertTrue(assigned.filter(title="Follow-up date changed", message__contains="Nov 1, 2026").exists())
        self.assertFalse(Notification.objects.filter(user=self.owner, title="Follow-up date changed").exists())

    def test_owners_cannot_be_assigned(self):
        self._edit(assigned_to=str(self.owner.id))
        self.note.refresh_from_db()
        self.assertIsNone(self.note.assigned_to)

    def test_mark_done_and_reopen_are_tracked(self):
        self.http.post(reverse("mark-client-note-done", args=[self.note.id]))
        self.note.refresh_from_db()
        self.assertTrue(self.note.is_done)
        self.assertEqual(self.note.completed_by, self.owner)
        self.assertIsNotNone(self.note.completed_at)

        self.http.post(reverse("reopen-client-note", args=[self.note.id]))
        self.note.refresh_from_db()
        self.assertFalse(self.note.is_done)
        self.assertIsNone(self.note.completed_at)
        self.assertEqual(
            list(ClientNoteHistory.objects.order_by("id").values_list("action", flat=True)),
            ["completed", "reopened"],
        )

    def test_other_offices_cannot_edit_or_reopen(self):
        outsider_org = Organization.objects.create(name="Other PSB", city="NYC")
        outsider = User.objects.create_user(username="outsider", password="pw-12345")
        OrganizationMembership.objects.create(user=outsider, organization=outsider_org, role="owner", is_active=True)
        http = TestClient()
        http.force_login(outsider)
        response = http.post(reverse("edit-client-note", args=[self.note.id]), {"content": "hacked"})
        self.assertIn(response.status_code, {302, 403})
        http.post(reverse("reopen-client-note", args=[self.note.id]))
        self.note.refresh_from_db()
        self.assertEqual(self.note.content, "Call about the title")
        self.assertFalse(ClientNoteHistory.objects.exists())

    def test_edit_requires_post(self):
        response = self.http.get(reverse("edit-client-note", args=[self.note.id]))
        self.assertEqual(response.status_code, 405)

    def test_unsafe_next_url_is_ignored(self):
        response = self._edit(content="Updated", next="https://evil.example/")
        self.assertTrue(response["Location"].startswith(reverse("client-detail", args=[self.client_obj.id])))

    def test_profile_renders_system_notes_without_an_author(self):
        ClientNote.objects.create(client=self.client_obj, content="Merged profile from another record")
        response = self.http.get(reverse("client-detail", args=[self.client_obj.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System")

    def test_profile_shows_edit_form_history_and_status(self):
        self._edit(content="Call <b>today</b>", follow_up_date=(timezone.localdate() - timedelta(days=1)).isoformat())
        response = self.http.get(reverse("client-detail", args=[self.client_obj.id]))
        self.assertContains(response, reverse("edit-client-note", args=[self.note.id]))
        self.assertContains(response, "cpp-note is-overdue")
        self.assertContains(response, "Overdue")
        self.assertContains(response, "Edited")
        self.assertContains(response, "created the note")
        self.assertContains(response, "Call &lt;b&gt;today&lt;/b&gt;")
        self.assertNotContains(response, "Call <b>today</b>")
        self.assertContains(response, f'<option value="{self.agent.id}" selected>', html=False)
