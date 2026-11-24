"""Signed-in desk. Uses the project database."""

import json
from datetime import date
from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.insurance_quote_pipeline_models import InsuranceQuoteLead
from core.models import Organization, OrganizationMembership
from quoting.demo.scenarios import clean, mvr
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

    def _post(self, form, *, run, extra=()):
        pairs = []
        for key, value in form.items():
            if isinstance(value, list):
                pairs.extend((key, item) for item in value)
            else:
                pairs.append((key, value))
        pairs.append(("run", run))
        pairs.extend(extra)
        return self.client.post(
            reverse("ny-auto-quote"),
            urlencode(pairs),
            content_type="application/x-www-form-urlencoded",
        )

    def test_desk_runs_a_fixture_quote_and_saves_it(self):
        response = self.client.get(reverse("ny-auto-quote"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Maya"')
        self.assertContains(response, 'value="Hassan"')
        self.assertNotContains(response, 'type="password"')

        posted = self._post(clean(ny_today()), run="demo")
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

    def test_mvr_run_saves_stops_without_premiums(self):
        posted = self._post(mvr(ny_today()), run="demo")
        self.assertEqual(posted.status_code, 200)
        self.assertContains(posted, "motor vehicle report for Maya Hassan")
        self.assertNotContains(posted, "DEMO-PGR-")
        job = QuoteJob.objects.get()
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.attempts.count(), 3)
        self.assertFalse(job.attempts.exclude(status="blocked").exists())
        self.assertFalse(job.attempts.exclude(term_premium=None).exists())
        self.assertEqual(job.attempts.filter(blocker_code="mvr_required").count(), 3)

    def test_live_check_does_not_save_a_password_or_a_fixture_premium(self):
        secret = "hunter2-do-not-store"
        posted = self._post(
            clean(ny_today()),
            run="live",
            extra=(("portal_password", secret), ("PROGRESSIVE_AGENT_PORTAL_PASSWORD", secret)),
        )
        self.assertEqual(posted.status_code, 200)
        self.assertNotContains(posted, secret)
        self.assertNotContains(posted, "DEMO-PGR-")
        job = QuoteJob.objects.get()
        self.assertEqual(job.mode, "live")
        stored = json.dumps(job.intake)
        self.assertNotIn(secret, stored)
        self.assertNotIn("portal_password", stored)
        self.assertNotIn("PROGRESSIVE_AGENT_PORTAL_PASSWORD", stored)
        self.assertFalse(job.attempts.exclude(term_premium=None).exists())

    def test_agent_without_insurance_access_is_denied(self):
        agent = User.objects.create_user(username="quote-outsider", password="long-enough-password")
        OrganizationMembership.objects.create(
            user=agent,
            organization=self.org,
            role=OrganizationMembership.Role.AGENT,
            is_active=True,
            can_use_insurance=False,
        )
        self.client.force_login(agent)
        response = self.client.get(reverse("ny-auto-quote"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(QuoteJob.objects.count(), 0)

    def test_lead_prefill_leaves_unknown_driving_history_blank(self):
        lead = InsuranceQuoteLead.objects.create(
            organization=self.org,
            client_name="Ada Lovelace",
            phone="7185550100",
            street_address="1 Main Street",
            apartment="4B",
            city="Jamaica",
            state="NY",
            zip_code="11432",
            date_of_birth=date(1990, 1, 2),
            dl_number="999888777",
            vehicle_year="2020",
            vehicle_make="Honda",
            vehicle_model="Civic",
            vin="1HGCM82633A004352",
            coverage_type="liability",
            has_accident=True,
            has_prior=False,
        )
        response = self.client.get(reverse("ny-auto-quote"), {"lead": lead.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Ada"')
        self.assertContains(response, 'value="Lovelace"')
        self.assertContains(response, "1 Main Street, 4B")
        self.assertContains(response, "1HGCM82633A004352")
        self.assertContains(response, 'name="driver_1_violations" type="text" value=""')
        self.assertContains(response, 'name="driver_1_accidents" type="text" value=""')
        self.assertContains(response, 'value="none" selected>None</option>')

    def test_unassigned_agent_cannot_open_another_leads_quote(self):
        lead = InsuranceQuoteLead.objects.create(
            organization=self.org,
            client_name="Grace Hopper",
            phone="7185550199",
        )
        agent = User.objects.create_user(username="quote-agent", password="long-enough-password")
        OrganizationMembership.objects.create(
            user=agent,
            organization=self.org,
            role=OrganizationMembership.Role.AGENT,
            is_active=True,
            can_use_insurance=True,
        )
        self.client.force_login(agent)
        response = self.client.get(reverse("ny-auto-quote"), {"lead": lead.id})
        self.assertEqual(response.status_code, 403)
