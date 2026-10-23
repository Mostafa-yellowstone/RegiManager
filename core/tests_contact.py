from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from core.contact_inbox import contact_recipients
from core.models import ContactMessage

User = get_user_model()

VALID = {
    "name": "Dina Farouk",
    "email": "dina@example.com",
    "subject": "Request a demo",
    "message": "We run two PSB offices and want a demo.",
}


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CONTACT_INBOX_EMAIL="mail@regimanager.com",
)
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


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CONTACT_INBOX_EMAIL="mail@regimanager.com, owner@gmail.com",
    CONTACT_DIRECT_MX_HOST="regimanager-com.mail.protection.outlook.com",
)
class ContactDirectDeliveryTests(TestCase):
    def setUp(self):
        self.record = ContactMessage.objects.create(
            name="Dina", email="dina@example.com", subject="General inquiry", message="Hello"
        )

    def _deliver(self, send_effects):
        import smtplib

        from core.contact_inbox import deliver_contact_message

        sent_to = []

        def fake_send(message, fail_silently=False):
            sent_to.append(list(message.to))
            effect = send_effects.pop(0)
            if effect is not None:
                raise effect
            return 1

        login_error = smtplib.SMTPAuthenticationError(535, b"5.7.3 Authentication unsuccessful")
        effects = [login_error if e == "login" else e for e in send_effects]
        send_effects[:] = effects
        with mock.patch("django.core.mail.EmailMessage.send", autospec=True, side_effect=fake_send), mock.patch(
            "core.contact_inbox._direct_connection"
        ) as direct:
            ok = deliver_contact_message(self.record.id)
        self.record.refresh_from_db()
        return ok, sent_to, direct

    def test_login_rejected_falls_back_to_direct_delivery_to_own_domain(self):
        ok, sent_to, direct = self._deliver(["login", None])
        self.assertTrue(ok)
        self.assertTrue(self.record.email_sent)
        self.assertEqual(self.record.email_error, "")
        direct.assert_called_once()
        self.assertEqual(sent_to[1], ["mail@regimanager.com"])

    def test_both_routes_failing_records_both_errors(self):
        ok, _, _ = self._deliver(["login", OSError("port 25 blocked")])
        self.assertFalse(ok)
        self.assertFalse(self.record.email_sent)
        self.assertIn("535", self.record.email_error)
        self.assertIn("port 25 blocked", self.record.email_error)

    def test_login_working_never_uses_direct_route(self):
        ok, sent_to, direct = self._deliver([None])
        self.assertTrue(ok)
        direct.assert_not_called()
        self.assertEqual(sent_to[0], ["mail@regimanager.com", "owner@gmail.com"])

    @override_settings(CONTACT_DIRECT_MX_HOST="")
    def test_direct_route_can_be_disabled(self):
        ok, _, direct = self._deliver(["login"])
        self.assertFalse(ok)
        direct.assert_not_called()
        self.assertIn("535", self.record.email_error)


class ContactRecipientTests(TestCase):
    @override_settings(CONTACT_INBOX_EMAIL="", EMAIL_HOST_USER="sender@regimanager.com")
    def test_public_inbox_even_when_sending_from_another_mailbox(self):
        self.assertEqual(contact_recipients(), ["mail@regimanager.com"])

    @override_settings(CONTACT_INBOX_EMAIL=" a@regimanager.com , MAIL@regimanager.com, nonsense ")
    def test_extra_addresses_are_added_not_replacing(self):
        self.assertEqual(contact_recipients(), ["mail@regimanager.com", "a@regimanager.com"])

    @override_settings(CONTACT_INBOX_EMAIL="", EMAIL_HOST_USER="")
    def test_falls_back_to_public_inbox(self):
        self.assertEqual(contact_recipients(), ["mail@regimanager.com"])


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CONTACT_INBOX_EMAIL="mail@regimanager.com",
)
class ContactRetryTests(TestCase):
    def setUp(self):
        self.url = reverse("contact-messages")
        self.admin = User.objects.create_superuser("root_retry", "root@example.com", "pass12345")
        self.client.force_login(self.admin)
        self.failed = ContactMessage.objects.create(
            name="Omar", email="omar@example.com", subject="General inquiry",
            message="Please call me.", email_error="SMTPAuthenticationError: 535",
        )

    def test_retry_one_message(self):
        res = self.client.get(self.url)
        self.assertContains(res, "Retry email")
        self.assertContains(res, "mail@regimanager.com")
        self.client.post(self.url, {"message_id": self.failed.id, "action": "retry"})
        self.failed.refresh_from_db()
        self.assertTrue(self.failed.email_sent)
        self.assertEqual(self.failed.email_error, "")
        self.assertEqual(mail.outbox[0].reply_to, ["omar@example.com"])

    def test_retry_all(self):
        ContactMessage.objects.create(name="Lina", email="lina@example.com", subject="General inquiry", message="Hi")
        self.client.post(self.url, {"action": "retry_all"})
        self.assertEqual(ContactMessage.objects.filter(email_sent=False).count(), 0)
        self.assertEqual(len(mail.outbox), 2)

    def test_retry_failure_keeps_error(self):
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=OSError("still down")):
            self.client.post(self.url, {"message_id": self.failed.id, "action": "retry"})
        self.failed.refresh_from_db()
        self.assertFalse(self.failed.email_sent)
        self.assertIn("still down", self.failed.email_error)

    def test_management_command_sends_pending_and_test(self):
        out = StringIO()
        call_command("retry_contact_emails", stdout=out)
        self.assertIn("Emailed 1 of 1", out.getvalue())
        self.assertIn("mail@regimanager.com", out.getvalue())
        call_command("retry_contact_emails", "--test", stdout=out)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("delivery test", mail.outbox[1].subject)

    def test_non_superuser_cannot_retry(self):
        staff = User.objects.create_user("plain_retry", password="pass12345")
        self.client.force_login(staff)
        self.assertEqual(self.client.post(self.url, {"action": "retry_all"}).status_code, 404)
        self.assertEqual(len(mail.outbox), 0)


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
