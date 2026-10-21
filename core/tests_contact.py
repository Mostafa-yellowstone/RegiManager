from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import ContactMessage

User = get_user_model()

VALID = {
    "name": "Dina Farouk",
    "email": "dina@example.com",
    "subject": "Request a demo",
    "message": "We run two PSB offices and want a demo.",
}


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ContactPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("contact")

    def _post(self, **overrides):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, {**VALID, **overrides}, REMOTE_ADDR="93.184.216.34")

    def test_page_shows_hero_image(self):
        res = self.client.get(self.url)
        self.assertContains(res, "contact_hero.webp")

    def test_message_is_saved_and_emailed_with_reply_to(self):
        res = self._post()
        self.assertRedirects(res, self.url)
        record = ContactMessage.objects.get()
        self.assertEqual(record.email, "dina@example.com")
        self.assertEqual(str(record.ip_address), "93.184.216.34")
        self.assertTrue(record.email_sent)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["mail@regimanager.com"])
        self.assertEqual(sent.reply_to, ["dina@example.com"])
        self.assertIn("Request a demo", sent.subject)
        self.assertIn("two PSB offices", sent.body)

    def test_smtp_failure_still_saves_and_thanks_visitor(self):
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=OSError("Connection unexpectedly closed")):
            res = self._post()
        self.assertRedirects(res, self.url, fetch_redirect_response=False)
        record = ContactMessage.objects.get()
        self.assertFalse(record.email_sent)
        self.assertIn("Connection unexpectedly closed", record.email_error)
        page = self.client.get(self.url)
        self.assertContains(page, "Message received")
        self.assertNotContains(page, "We could not send that")

    def test_invalid_input_is_rejected(self):
        for overrides in ({"email": "not-an-email"}, {"name": "  "}, {"message": ""}, {"email": "a@b"}):
            res = self._post(**overrides)
            self.assertEqual(res.status_code, 200)
            self.assertContains(res, "Add your name, a real email, and a message.")
        self.assertFalse(ContactMessage.objects.exists())

    def test_unknown_topic_and_header_injection_are_neutralised(self):
        self._post(subject="Evil\r\nBcc: victim@example.com", name="Dina\r\nBcc: x@example.com")
        record = ContactMessage.objects.get()
        self.assertEqual(record.subject, "General inquiry")
        self.assertNotIn("\n", record.name)
        self.assertNotIn("\n", mail.outbox[0].subject)

    def test_honeypot_drops_bots(self):
        self._post(company_website="http://spam.example")
        self.assertFalse(ContactMessage.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_rate_limited_after_five_posts(self):
        for _ in range(5):
            self._post()
        res = self._post()
        self.assertEqual(res.status_code, 429)
        self.assertEqual(ContactMessage.objects.count(), 5)


class ContactInboxTests(TestCase):
    def setUp(self):
        self.url = reverse("contact-messages")
        self.admin = User.objects.create_superuser("root_contact", "root@example.com", "pass12345")
        self.staff = User.objects.create_user("plain_contact", password="pass12345")
        self.msg = ContactMessage.objects.create(
            name="Dina <script>", email="dina@example.com", subject="General inquiry",
            message="Hello <b>team</b>", email_error="OSError: closed",
        )

    def test_only_superusers_can_open(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_inbox_lists_and_escapes_messages(self):
        self.client.force_login(self.admin)
        res = self.client.get(self.url)
        self.assertContains(res, "Dina &lt;script&gt;")
        self.assertContains(res, "Hello &lt;b&gt;team&lt;/b&gt;")
        self.assertContains(res, "could not be emailed")
        self.assertNotContains(res, "Dina <script>")

    def test_mark_handled_and_reopen(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {"message_id": self.msg.id, "action": "handled"})
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.is_handled)
        self.assertNotContains(self.client.get(self.url), "dina@example.com")
        self.assertContains(self.client.get(self.url + "?show=all"), "dina@example.com")
        self.client.post(self.url, {"message_id": self.msg.id, "action": "reopen"})
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.is_handled)
        self.assertEqual(self.client.post(self.url, {"message_id": "x"}).status_code, 404)
