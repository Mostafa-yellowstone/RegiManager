from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.agent_portal_models import AgentAttendanceSession
from core.finance_hub_metrics import build_payment_cards_for_range
from core.insurance_quote_distribution import distribution_channel_payload, eligible_agents_for_auto
from core.insurance_quote_pipeline_models import InsuranceAgentOffDay
from core.models import Organization, OrganizationMembership, ServiceRecord

TEST_SETTINGS = dict(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)


@override_settings(**TEST_SETTINGS)
class HealthAndMediaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="hard-user", password="x")

    def test_healthz_reports_database_and_cache(self):
        res = self.client.get(reverse("healthz"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "checks": {"database": "ok", "cache": "ok"}})

    def media(self, path):
        return self.client.get(reverse("media-auth"), HTTP_X_ORIGINAL_URI=path).status_code

    def test_private_documents_need_a_signed_in_user(self):
        self.assertEqual(self.media("/media/client_docs/mv82/license.pdf"), 401)
        self.assertEqual(self.media("/media/insurance_policy_documents/dec.pdf?x=1"), 401)
        self.client.force_login(self.user)
        self.assertEqual(self.media("/media/client_docs/mv82/license.pdf"), 204)

    def test_logos_and_email_images_stay_public(self):
        self.assertEqual(self.media("/media/organization_logos/logo.png"), 204)
        self.assertEqual(self.media("/media/email_marketing/2026/11/banner.png"), 204)
        self.assertEqual(self.media("/media/agent_profiles/me.jpg"), 204)

    def test_path_tricks_are_refused(self):
        self.assertEqual(self.media("/media/organization_logos/../client_docs/x.pdf"), 403)
        self.assertEqual(self.media("/media/organization_logos/%2e%2e/client_docs/x.pdf"), 403)
        self.assertEqual(self.media("/static/x.css"), 403)


@override_settings(**TEST_SETTINGS)
class PortalEndpointTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Hard Org", city="NYC")
        self.owner = User.objects.create_user(username="hard-owner", password="x")
        self.membership = OrganizationMembership.objects.create(
            user=self.owner, organization=self.org, role=OrganizationMembership.Role.OWNER, is_active=True,
            can_trigger_automation=True,
        )
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_org_id"] = self.org.id
        session.save()

    def test_latest_news_endpoint_answers(self):
        res = self.client.get(reverse("get-latest-news"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("id", res.json())

    def test_automation_scan_only_runs_on_post(self):
        with patch("core.tasks.check_registration_reminders.delay") as delay:
            self.assertEqual(self.client.get(reverse("run-automation")).status_code, 405)
            delay.assert_not_called()
            res = self.client.post(reverse("run-automation"))
        self.assertEqual(res.status_code, 302)
        delay.assert_called_once()

    def test_policy_filters_ignore_non_numeric_ids(self):
        res = self.client.get(reverse("insurance-policies"), {"agent": "none", "insurance_company": "abc"})
        self.assertEqual(res.status_code, 200)


@override_settings(**TEST_SETTINGS)
class QueryCountTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Query Org", city="NYC")
        self.work = date(2026, 8, 10)

    def add_agents(self, count):
        for i in range(count):
            user = User.objects.create_user(username=f"q-agent-{self.org.id}-{i}-{User.objects.count()}", password="x")
            member = OrganizationMembership.objects.create(
                user=user, organization=self.org, role=OrganizationMembership.Role.INSURANCE_AGENT,
                is_active=True, can_use_insurance=True, can_deal_with_insurance=True,
            )
            AgentAttendanceSession.objects.create(
                membership=member, organization=self.org, work_date=self.work,
                opened_at=f"{self.work.isoformat()}T09:00:00-04:00",
            )

    def payload_queries(self):
        with CaptureQueriesContext(connection) as ctx:
            distribution_channel_payload(self.org, work_date=self.work)
        return len(ctx.captured_queries)

    def test_distribution_queries_do_not_grow_with_agents(self):
        self.add_agents(2)
        self.payload_queries()
        few = self.payload_queries()
        self.add_agents(10)
        self.assertEqual(self.payload_queries(), few)

    def test_off_and_checked_out_agents_are_skipped(self):
        self.add_agents(3)
        members = list(OrganizationMembership.objects.filter(organization=self.org).order_by("id"))
        InsuranceAgentOffDay.objects.create(organization=self.org, membership=members[0], off_date=self.work)
        AgentAttendanceSession.objects.filter(membership=members[1]).update(
            closed_at=f"{self.work.isoformat()}T17:00:00-04:00"
        )
        eligible = eligible_agents_for_auto(self.org, work_date=self.work)
        self.assertEqual([m.id for m in eligible], [members[2].id])

    def test_finance_cards_batch_refund_lookups(self):
        owner = User.objects.create_user(username="fin-owner", password="x")
        day = date(2026, 8, 3)

        def record(**extra):
            return ServiceRecord.objects.create(
                organization=self.org, client_name="X", service_type="vehicle_registration",
                transaction_date=day, handled_by=owner, payment_method="cash", **extra,
            )

        refunded = record(paid_amount=Decimal("0"), service_fee=Decimal("40"))
        record(status="refund", refunded_from=refunded, paid_amount=Decimal("0"))
        record(paid_amount=Decimal("25"))
        records = ServiceRecord.objects.filter(organization=self.org)
        cards, total = build_payment_cards_for_range(records, day, day)
        self.assertEqual(total, Decimal("25"))
        for _ in range(10):
            record(paid_amount=Decimal("0"), service_fee=Decimal("5"))
        with CaptureQueriesContext(connection) as ctx:
            build_payment_cards_for_range(records, day - timedelta(days=1), day)
        self.assertLessEqual(len(ctx.captured_queries), 3)
