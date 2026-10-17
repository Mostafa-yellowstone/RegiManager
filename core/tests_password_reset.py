import re
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import Client as DjangoClient, TestCase, override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token

from core.models import Organization, OrganizationMembership

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "password-reset-tests"}}
PUBLIC_IP = "93.184.216.34"
OTHER_IP = "93.184.216.77"
NEW_PASSWORD = "Fresh-Lantern-Rocket-47"

BASE_SETTINGS = dict(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    CACHES=LOCMEM,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="RegiManager <no-reply@regimanager.test>",
)


def _reset_link(message):
    match = re.search(r"https?://[^/\s]+(/auth/reset/[^/\s]+/[^/\s]+/)", message.body)
    assert match, message.body
    return match.group(1)


@override_settings(**BASE_SETTINGS, RATE_LIMIT_ENABLED=False)
class PasswordResetFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(name="Reset PSB", city="NYC")
        self.user = User.objects.create_user(
            username="resetme", email="ResetMe@Example.com", password="Old-Password-123", first_name="Rita"
        )
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, role=OrganizationMembership.Role.OWNER, is_active=True
        )
        self.http = DjangoClient(REMOTE_ADDR=PUBLIC_IP)

    def tearDown(self):
        cache.clear()

    def _request_reset(self, email="resetme@example.com", client=None):
        return (client or self.http).post(reverse("password-reset"), {"email": email})

    def test_login_page_links_to_password_reset_and_has_centered_loading_state(self):
        response = self.http.get(reverse("login"))
        self.assertContains(response, reverse("password-reset"))
        self.assertContains(response, "Forgot password?")
        self.assertContains(response, 'data-loading-text="Signing in…"')
        self.assertContains(response, 'class="btn-spinner"')

    def test_signup_page_has_loading_text_without_forgot_link(self):
        response = self.http.get(reverse("member-signup"))
        self.assertContains(response, 'data-loading-text="Creating account…"')
        self.assertNotContains(response, "Forgot password?")

    def test_invalid_credentials_show_an_error_message(self):
        response = self.http.post(reverse("login"), {"username": "resetme", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "auth-alert-error")

    def test_reset_request_page_renders(self):
        response = self.http.get(reverse("password-reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reset your password")
        self.assertContains(response, 'type="email"')
        self.assertContains(response, 'data-loading-text="Sending link…"')

    def test_known_email_receives_branded_reset_link_case_insensitively(self):
        response = self._request_reset("RESETME@example.com")
        self.assertRedirects(response, reverse("password-reset-done"))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])
        self.assertEqual(message.subject, "Reset your RegiManager password")
        self.assertIn("Rita", message.body)
        self.assertIn("/auth/reset/", message.body)
        html = message.alternatives[0][0]
        self.assertIn("Set a new password", html)
        self.assertIn(_reset_link(message), html)

    def test_unknown_email_gets_identical_response_and_no_email(self):
        known = self._request_reset()
        unknown = self._request_reset("nobody@example.com")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known["Location"], unknown["Location"])
        self.assertEqual(len(mail.outbox), 1)

    def test_inactive_user_gets_no_email(self):
        self.user.is_active = False
        self.user.save()
        self._request_reset()
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_email_shows_form_error(self):
        response = self._request_reset("not-an-email")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "has-error")
        self.assertEqual(len(mail.outbox), 0)

    def test_done_page_does_not_reveal_whether_account_exists(self):
        response = self.http.get(reverse("password-reset-done"))
        self.assertContains(response, "If an account matches that email")
        self.assertContains(response, reverse("login"))

    def test_full_reset_sets_new_password_and_old_one_stops_working(self):
        self._request_reset()
        link = _reset_link(mail.outbox[0])

        form_page = self.http.get(link, follow=True)
        self.assertEqual(form_page.status_code, 200)
        self.assertContains(form_page, "Set a new password")
        set_password_url = form_page.redirect_chain[-1][0]
        self.assertNotIn(link.rstrip("/").split("/")[-1], set_password_url)

        done = self.http.post(set_password_url, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
        self.assertRedirects(done, reverse("password-reset-complete"))
        self.assertContains(self.http.get(reverse("password-reset-complete")), "Password updated")
        self.assertNotIn("_auth_user_id", self.http.session)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertFalse(self.user.check_password("Old-Password-123"))

        fresh = DjangoClient(REMOTE_ADDR=OTHER_IP)
        fresh.post(reverse("login"), {"username": "resetme", "password": NEW_PASSWORD})
        self.assertEqual(int(fresh.session["_auth_user_id"]), self.user.pk)

    def test_reset_link_only_works_once(self):
        self._request_reset()
        link = _reset_link(mail.outbox[0])
        page = self.http.get(link, follow=True)
        self.http.post(
            page.redirect_chain[-1][0], {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        )
        reused = DjangoClient(REMOTE_ADDR=PUBLIC_IP).get(link, follow=True)
        self.assertContains(reused, "Link expired")
        self.assertContains(reused, reverse("password-reset"))
        self.assertNotContains(reused, 'name="new_password1"')

    def test_tampered_token_shows_expired_page(self):
        response = self.http.get(
            reverse("password-reset-confirm", kwargs={"uidb64": "MQ", "token": "bad-token"}), follow=True
        )
        self.assertContains(response, "Link expired")
        self.assertNotContains(response, 'name="new_password1"')

    def test_expired_token_is_rejected(self):
        self._request_reset()
        link = _reset_link(mail.outbox[0])
        with mock.patch("django.contrib.auth.tokens.PasswordResetTokenGenerator._now") as now:
            now.return_value = datetime.now() + timedelta(hours=2)
            response = self.http.get(link, follow=True)
        self.assertContains(response, "Link expired")

    def test_weak_or_mismatched_password_is_rejected(self):
        self._request_reset()
        page = self.http.get(_reset_link(mail.outbox[0]), follow=True)
        url = page.redirect_chain[-1][0]
        mismatch = self.http.post(url, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD + "x"})
        self.assertEqual(mismatch.status_code, 200)
        self.assertContains(mismatch, "has-error")
        weak = self.http.post(url, {"new_password1": "123", "new_password2": "123"})
        self.assertEqual(weak.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old-Password-123"))

    def test_reset_revokes_existing_api_tokens(self):
        Token.objects.create(user=self.user)
        self._request_reset()
        page = self.http.get(_reset_link(mail.outbox[0]), follow=True)
        self.http.post(page.redirect_chain[-1][0], {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_reset_emails_are_throttled_per_address(self):
        for _ in range(5):
            response = self._request_reset()
            self.assertRedirects(response, reverse("password-reset-done"))
        self.assertEqual(len(mail.outbox), 3)

    def test_successful_reset_clears_account_lockout(self):
        attacker = DjangoClient(REMOTE_ADDR=OTHER_IP)
        for _ in range(5):
            attacker.post(reverse("login"), {"username": "resetme", "password": "wrong"})

        self._request_reset()
        page = self.http.get(_reset_link(mail.outbox[0]), follow=True)
        self.http.post(page.redirect_chain[-1][0], {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})

        owner = DjangoClient(REMOTE_ADDR=PUBLIC_IP)
        owner.post(reverse("login"), {"username": "resetme", "password": NEW_PASSWORD})
        self.assertEqual(int(owner.session["_auth_user_id"]), self.user.pk)


@override_settings(**BASE_SETTINGS, RATE_LIMIT_ENABLED=True)
class PasswordResetRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        clock = mock.patch("core.rate_limit_middleware.time.time", return_value=1_800_000_000.0)
        clock.start()
        self.addCleanup(clock.stop)

    def tearDown(self):
        cache.clear()

    def test_reset_request_posts_are_rate_limited_per_ip(self):
        http = DjangoClient(REMOTE_ADDR=PUBLIC_IP)
        statuses = [
            http.post(reverse("password-reset"), {"email": f"user{i}@example.com"}).status_code for i in range(12)
        ]
        self.assertIn(429, statuses)

    def test_reset_confirm_posts_are_rate_limited_per_ip(self):
        http = DjangoClient(REMOTE_ADDR=PUBLIC_IP)
        url = reverse("password-reset-confirm", kwargs={"uidb64": "MQ", "token": "set-password"})
        statuses = [http.post(url, {"new_password1": "x", "new_password2": "x"}).status_code for _ in range(12)]
        self.assertIn(429, statuses)

    def test_viewing_reset_pages_is_not_limited_by_auth_rule(self):
        http = DjangoClient(REMOTE_ADDR=PUBLIC_IP)
        statuses = [http.get(reverse("password-reset")).status_code for _ in range(15)]
        self.assertNotIn(429, statuses)
