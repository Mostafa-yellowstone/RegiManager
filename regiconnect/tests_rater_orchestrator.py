from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.utils import timezone

from core.insurance_quote_pipeline_models import InsuranceQuoteLead
from core.models import Client, InsuranceCompany, Organization, OrganizationMembership, Vehicle
from core.role_permissions import apply_role_permission_pack

from regiconnect.catalog import ensure_builtin_connectors
from regiconnect.models import (
    Appointment,
    AppetiteRule,
    CanonicalQuote,
    Connection,
    Connector,
    ConnectorJob,
    MarketProfile,
    ProducerCode,
    RatingError,
    RatingExtension,
    RatingJob,
    RatingRequest,
)
from django.urls import reverse

from regiconnect.rater import create_rating_request, rating_results, resume_pending_jobs, select_quote, start_rating


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class RegiRaterOrchestratorTests(TestCase):
    def setUp(self):
        ensure_builtin_connectors()
        self.org = Organization.objects.create(name="Orch Org", city="NYC")
        self.user = User.objects.create_user("orchowner", password="password123")
        membership = OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        apply_role_permission_pack(membership)
        self.client_row = Client.objects.create(
            organization=self.org,
            first_name="Luis",
            last_name="Chen",
            phone_number="5553334444",
            state="NY",
        )
        self.car = Vehicle.objects.create(
            client=self.client_row,
            vin="1HGCM82633A004352",
            year=2018,
            make="Honda",
            model="Civic",
        )
        self.mock = Connector.objects.get(slug="mock")
        self.market = self._market("Voluntary Mock A", MarketProfile.MarketChannel.VOLUNTARY)
        self._activate(self.market, self.mock)
        self.aip = self._market("NY AIP Tracking", MarketProfile.MarketChannel.ASSIGNED_RISK, market_type=MarketProfile.MarketType.OTHER)

    def _market(self, name, channel, market_type=MarketProfile.MarketType.CARRIER):
        company = InsuranceCompany.objects.create(organization=self.org, name=name)
        return MarketProfile.objects.create(
            organization=self.org,
            company=company,
            market_type=market_type,
            market_channel=channel,
            status=MarketProfile.Status.ACTIVE,
            states=["NY"],
            lines_of_business=["auto_personal"],
        )

    def _activate(self, market, connector):
        Appointment.objects.create(
            organization=self.org,
            market=market,
            state="NY",
            line_of_business="auto_personal",
            status=Appointment.Status.ACTIVE,
            effective_date=timezone.localdate(),
        )
        ProducerCode.objects.create(
            organization=self.org,
            market=market,
            code=f"P-{market.id}",
            state="NY",
            line_of_business="auto_personal",
        )
        return Connection.objects.create(
            organization=self.org,
            market=market,
            connector=connector,
            environment=Connection.Environment.SANDBOX,
            status=Connection.Status.ACTIVE,
            capabilities=connector.capabilities,
        )

    def _request(self, **kwargs):
        return create_rating_request(
            organization=self.org,
            client=self.client_row,
            actor=self.user,
            vehicles=[self.car],
            coverage={"type": "full"},
            **kwargs,
        )

    def test_shop_eligible_mock_does_not_create_pipeline_lead(self):
        request = self._request(idempotency_key="orch-1")
        start_rating(request, actor=self.user)
        request.refresh_from_db()
        self.assertEqual(request.status, RatingRequest.Status.COMPLETED)
        job = request.jobs.get(market=self.market)
        self.assertEqual(job.status, RatingJob.Status.QUOTED)
        self.assertEqual(job.eligibility, RatingJob.Eligibility.ELIGIBLE)
        quote = CanonicalQuote.objects.get(rating_job=job)
        self.assertEqual(quote.quote_source, CanonicalQuote.QuoteSource.MOCK)
        self.assertEqual(quote.premium_class, CanonicalQuote.PremiumClass.ESTIMATED)
        self.assertEqual(InsuranceQuoteLead.objects.filter(organization=self.org).count(), 0)
        aip_job = request.jobs.get(market=self.aip)
        self.assertEqual(aip_job.status, RatingJob.Status.EXCLUDED)
        self.assertIn("Assigned Risk", aip_job.eligibility_reason)

    def test_unspecified_connector_is_unavailable(self):
        unspecified = Connector.objects.get(slug="unspecified")
        skeleton_market = self._market("No Spec Mutual", MarketProfile.MarketChannel.VOLUNTARY)
        self._activate(skeleton_market, unspecified)
        request = self._request(idempotency_key="orch-spec")
        start_rating(request, actor=self.user, market_ids=[skeleton_market.id])
        request.refresh_from_db()
        self.assertEqual(request.status, RatingRequest.Status.NO_MARKET)
        job = request.jobs.get(market=skeleton_market)
        self.assertEqual(job.eligibility, RatingJob.Eligibility.UNAVAILABLE)
        self.assertIn("official", job.eligibility_reason.lower())

    def test_partial_then_complete_with_decline_and_quote(self):
        other = self._market("Voluntary Mock B", MarketProfile.MarketChannel.VOLUNTARY)
        self._activate(other, self.mock)
        request = self._request(idempotency_key="orch-mix")
        RatingExtension.objects.create(
            rating_request=request,
            market=other,
            extra={"scenario": "decline"},
        )
        start_rating(request, actor=self.user, market_ids=[self.market.id, other.id])
        request.refresh_from_db()
        self.assertEqual(request.status, RatingRequest.Status.COMPLETED)
        statuses = set(request.jobs.values_list("status", flat=True))
        self.assertIn(RatingJob.Status.QUOTED, statuses)
        self.assertIn(RatingJob.Status.DECLINED, statuses)
        self.assertEqual(CanonicalQuote.objects.filter(rating_request=request).count(), 1)
        results = rating_results(request)
        self.assertEqual(results["quotes"][0]["quote_source"], "mock")

    def test_start_is_idempotent(self):
        request = self._request(idempotency_key="orch-idemp")
        start_rating(request, actor=self.user, market_ids=[self.market.id])
        start_rating(request, actor=self.user, market_ids=[self.market.id])
        self.assertEqual(request.jobs.filter(market=self.market).count(), 1)
        self.assertEqual(CanonicalQuote.objects.filter(rating_request=request).count(), 1)

    def test_retryable_timeout_does_not_mark_job_failed(self):
        request = self._request(idempotency_key="orch-to", extra={"scenario": "timeout"})
        start_rating(request, actor=self.user, market_ids=[self.market.id])
        request.refresh_from_db()
        job = request.jobs.get(market=self.market)
        job.refresh_from_db()
        self.assertEqual(job.status, RatingJob.Status.RATING)
        self.assertTrue(RatingError.objects.filter(rating_job=job, retryable=True).exists())
        connector_job = ConnectorJob.objects.get(pk=job.connector_job_id)
        self.assertEqual(connector_job.status, ConnectorJob.Status.RETRYING)
        self.assertNotEqual(request.status, RatingRequest.Status.COMPLETED)

    def test_appetite_ineligible_is_explained(self):
        AppetiteRule.objects.create(
            organization=self.org,
            market=self.market,
            name="NY auto closed",
            criteria=[{"field": "state", "op": "eq", "value": "NY"}],
            result_on_match="ineligible",
        )
        request = self._request(idempotency_key="orch-app")
        start_rating(request, actor=self.user, market_ids=[self.market.id])
        request.refresh_from_db()
        self.assertEqual(request.status, RatingRequest.Status.NO_MARKET)
        job = request.jobs.get(market=self.market)
        self.assertEqual(job.eligibility, RatingJob.Eligibility.INELIGIBLE)
        self.assertIn("matched", job.eligibility_reason.lower())

    def test_mock_refer_decline_invalid_and_delayed_quote(self):
        referred = self._request(idempotency_key="orch-ref", extra={"scenario": "refer"})
        start_rating(referred, actor=self.user, market_ids=[self.market.id])
        referred.refresh_from_db()
        self.assertEqual(referred.jobs.get().status, RatingJob.Status.REFERRED)

        invalid = self._request(idempotency_key="orch-inv", extra={"scenario": "invalid"})
        start_rating(invalid, actor=self.user, market_ids=[self.market.id])
        invalid.refresh_from_db()
        self.assertEqual(invalid.jobs.get().status, RatingJob.Status.FAILED)
        err = RatingError.objects.filter(rating_request=invalid).first()
        self.assertIsNotNone(err)
        self.assertNotIn("Traceback", err.agent_message)

        delayed = self._request(idempotency_key="orch-delay", extra={"scenario": "delay"})
        start_rating(delayed, actor=self.user, market_ids=[self.market.id])
        delayed.refresh_from_db()
        self.assertEqual(delayed.status, RatingRequest.Status.RATING)
        self.assertFalse(CanonicalQuote.objects.filter(rating_request=delayed).exists())
        resume_pending_jobs(delayed, actor=self.user)
        delayed.refresh_from_db()
        self.assertEqual(delayed.status, RatingRequest.Status.COMPLETED)
        quote = CanonicalQuote.objects.get(rating_request=delayed)
        self.assertEqual(quote.quote_source, CanonicalQuote.QuoteSource.MOCK)

    def test_select_quote_feeds_existing_pipeline_once(self):
        request = self._request(idempotency_key="orch-sel")
        start_rating(request, actor=self.user, market_ids=[self.market.id])
        quote = CanonicalQuote.objects.get(rating_request=request)
        lead = select_quote(quote, actor=self.user)
        self.assertEqual(lead.regi_connectivity.quote_source, "regi_rater")
        self.assertEqual(lead.regi_connectivity.premium, quote.premium)
        self.assertIn("MOCK", lead.notes)
        select_quote(quote, actor=self.user)
        self.assertEqual(InsuranceQuoteLead.objects.filter(organization=self.org).count(), 1)
        quote.refresh_from_db()
        self.assertEqual(quote.status, CanonicalQuote.Status.SELECTED)

    def test_ui_start_and_select_quote(self):
        self.client.login(username="orchowner", password="password123")
        from core.models import Space

        space = Space.objects.create(organization=self.org, key="insurance", label="Insurance")
        from core.models import OrganizationMembership

        membership = OrganizationMembership.objects.get(user=self.user, organization=self.org)
        membership.accessible_spaces.add(space)
        page = self.client.get(reverse("inventory-detail", args=[space.id]))
        self.assertContains(page, "Regi Rater")
        self.assertContains(page, "MOCK / TEST")
        start = self.client.post(
            reverse("regiconnect:rater-start"),
            {
                "organization": self.org.id,
                "client_id": self.client_row.id,
                "vehicle_id": self.car.id,
                "coverage_type": "full",
                "state": "NY",
                "line_of_business": "auto_personal",
                "market_id": self.market.id,
            },
        )
        self.assertEqual(start.status_code, 302)
        self.assertIn("tab=regi-rater", start["Location"])
        request = RatingRequest.objects.get(organization=self.org)
        quote = CanonicalQuote.objects.get(rating_request=request)
        selected = self.client.post(
            reverse("regiconnect:rater-select", args=[quote.id]),
            {"organization": self.org.id},
        )
        self.assertEqual(selected.status_code, 302)
        self.assertIn("tab=quote-pipeline", selected["Location"])
        lead = InsuranceQuoteLead.objects.get(organization=self.org)
        self.assertEqual(lead.regi_connectivity.quote_id, quote.id)
