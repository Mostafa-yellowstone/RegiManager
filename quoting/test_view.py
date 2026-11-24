"""Signed-in desk. Uses the project database."""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Organization, OrganizationMembership
from quoting.demo.scenarios import clean
from quoting.intake import ny_today
from quoting.models import QuoteAttempt, QuoteJob


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class QuotingDeskTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Quote Org", city="Jamaica")
        self.owner = User.objects.create_user(username="quote-owner", password="long-enough-password")
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client.force_login(self.owner)

    def test_desk_runs_a_fixture_quote_and_saves_it(self):
        response = self.client.get(reverse("ny-auto-quote"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Maya"')
        self.assertContains(response, 'value="Hassan"')
        self.assertNotContains(response, 'type="password"')

        from urllib.parse import urlencode

        form = clean(ny_today())
        pairs = []
        for key, value in form.items():
            if isinstance(value, list):
                pairs.extend((key, item) for item in value)
            else:
                pairs.append((key, value))
        pairs.append(("run", "demo"))
        posted = self.client.post(
            reverse("ny-auto-quote"),
            urlencode(pairs),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(posted.status_code, 200)
        self.assertContains(posted, "DEMO-PGR-")
        self.assertContains(posted, "producer certification that a voluntary carrier declined")
        job = QuoteJob.objects.get()
        self.assertEqual(job.organization, self.org)
        self.assertEqual(job.applicant_label, "Maya Hassan")
        self.assertEqual(job.attempts.count(), 3)
        self.assertEqual(job.attempts.filter(status="quoted").count(), 2)
        stopped = QuoteAttempt.objects.get(carrier_key="nyaip")
        self.assertEqual(stopped.term_premium, None)
        self.assertNotIn("PASSWORD=", posted.content.decode())

    def test_anonymous_user_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("ny-auto-quote"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"])
