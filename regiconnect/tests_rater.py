from django.test import TestCase, override_settings
from django.contrib.auth.models import User

from core.models import Client, InsuranceCompany, Organization, OrganizationMembership, Vehicle
from core.role_permissions import apply_role_permission_pack

from regiconnect.catalog import ensure_builtin_connectors
from regiconnect.models import (
    CanonicalQuote,
    Connection,
    ConnectAuditEvent,
    MarketProfile,
    OutboxEvent,
    RatingJob,
    RatingRequest,
)
from regiconnect.rater import (
    IllegalRatingTransition,
    add_rating_job,
    append_quote_version,
    create_rating_request,
    transition_rating_request,
)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class RegiRaterFoundationTests(TestCase):
    def setUp(self):
        ensure_builtin_connectors()
        self.org = Organization.objects.create(name="Rater Org", city="NYC")
        self.other = Organization.objects.create(name="Other Rater Org", city="NYC")
        self.user = User.objects.create_user("raterowner", password="password123")
        membership = OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        apply_role_permission_pack(membership)
        self.client_row = Client.objects.create(
            organization=self.org,
            first_name="Ana",
            last_name="Rivera",
            phone_number="5550001111",
            state="NY",
        )
        self.other_client = Client.objects.create(
            organization=self.other,
            first_name="Other",
            last_name="Person",
            phone_number="5550002222",
            state="NY",
        )
        self.car = Vehicle.objects.create(
            client=self.client_row,
            vin="1HGCM82633A004352",
            year=2018,
            make="Honda",
            model="Civic",
        )
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Voluntary Mock Co")
        self.market = MarketProfile.objects.create(
            organization=self.org,
            company=self.company,
            market_type=MarketProfile.MarketType.CARRIER,
            market_channel=MarketProfile.MarketChannel.VOLUNTARY,
            status=MarketProfile.Status.ACTIVE,
            states=["NY"],
            lines_of_business=["auto_personal"],
        )
        self.aip_company = InsuranceCompany.objects.create(organization=self.org, name="NY AIP Tracking")
        self.aip_market = MarketProfile.objects.create(
            organization=self.org,
            company=self.aip_company,
            market_type=MarketProfile.MarketType.OTHER,
            market_channel=MarketProfile.MarketChannel.ASSIGNED_RISK,
            status=MarketProfile.Status.ACTIVE,
            states=["NY"],
            lines_of_business=["auto_personal"],
        )

    def _connection(self):
        from regiconnect.models import Connector

        return Connection.objects.create(
            organization=self.org,
            market=self.market,
            connector=Connector.objects.get(slug="mock"),
            environment=Connection.Environment.SANDBOX,
            status=Connection.Status.ACTIVE,
        )

    def test_create_request_reuses_crm_and_is_idempotent(self):
        first = create_rating_request(
            organization=self.org,
            client=self.client_row,
            actor=self.user,
            vehicles=[self.car],
            coverage={"type": "full"},
            idempotency_key="rate-ana-1",
        )
        second = create_rating_request(
            organization=self.org,
            client=self.client_row,
            actor=self.user,
            vehicles=[self.car],
            idempotency_key="rate-ana-1",
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(RatingRequest.objects.filter(organization=self.org).count(), 1)
        self.assertEqual(first.canonical_snapshot["driver"]["client_id"], self.client_row.id)
        self.assertEqual(first.canonical_snapshot["vehicle"]["vin"], "1HGCM82633A004352")
        self.assertTrue(
            ConnectAuditEvent.objects.filter(
                organization=self.org, action="rating_request_created"
            ).exists()
        )
        self.assertTrue(
            OutboxEvent.objects.filter(
                organization=self.org, event_type="RatingRequestCreated"
            ).exists()
        )

    def test_cannot_attach_other_tenant_client(self):
        with self.assertRaises(ValueError):
            create_rating_request(organization=self.org, client=self.other_client, actor=self.user)

    def test_state_machine_rejects_illegal_jump(self):
        request = create_rating_request(
            organization=self.org,
            client=self.client_row,
            actor=self.user,
            idempotency_key="rate-sm-1",
        )
        with self.assertRaises(IllegalRatingTransition):
            transition_rating_request(request, RatingRequest.Status.COMPLETED)
        transition_rating_request(request, RatingRequest.Status.VALIDATING)
        transition_rating_request(request, RatingRequest.Status.ELIGIBILITY_CHECK)
        transition_rating_request(request, RatingRequest.Status.READY)
        self.assertEqual(request.status, RatingRequest.Status.READY)

    def test_assigned_risk_is_not_voluntary(self):
        self.assertEqual(self.market.market_channel, MarketProfile.MarketChannel.VOLUNTARY)
        self.assertEqual(self.aip_market.market_channel, MarketProfile.MarketChannel.ASSIGNED_RISK)

    def test_quote_versions_never_overwrite_and_mock_is_labeled(self):
        request = create_rating_request(
            organization=self.org,
            client=self.client_row,
            actor=self.user,
            vehicles=[self.car],
            idempotency_key="rate-q-1",
        )
        connection = self._connection()
        job = add_rating_job(
            request,
            market=self.market,
            connection=connection,
            eligibility=RatingJob.Eligibility.ELIGIBLE,
            eligibility_reason="NY Personal Auto appointment active.",
            status=RatingJob.Status.QUOTED,
            actor=self.user,
        )
        v1 = append_quote_version(
            organization=self.org,
            market=self.market,
            rating_request=request,
            rating_job=job,
            premium="2300.00",
            quote_source=CanonicalQuote.QuoteSource.MOCK,
            premium_class=CanonicalQuote.PremiumClass.ESTIMATED,
            provider_slug="mock",
            environment=Connection.Environment.SANDBOX,
        )
        v2 = append_quote_version(
            organization=self.org,
            market=self.market,
            rating_request=request,
            rating_job=job,
            premium="2360.00",
            quote_source=CanonicalQuote.QuoteSource.MOCK,
            premium_class=CanonicalQuote.PremiumClass.ESTIMATED,
            provider_slug="mock",
        )
        self.assertEqual(v1.version, 1)
        self.assertEqual(v2.version, 2)
        self.assertEqual(CanonicalQuote.objects.get(pk=v1.pk).premium, v1.premium)
        self.assertEqual(v1.quote_source, CanonicalQuote.QuoteSource.MOCK)
        self.assertNotEqual(v1.quote_source, CanonicalQuote.QuoteSource.DIRECT_CARRIER)
        self.assertEqual(v1.premium_class, CanonicalQuote.PremiumClass.ESTIMATED)

    def test_excluded_market_stores_reason(self):
        request = create_rating_request(
            organization=self.org,
            client=self.client_row,
            actor=self.user,
            idempotency_key="rate-ex-1",
        )
        job = add_rating_job(
            request,
            market=self.aip_market,
            eligibility=RatingJob.Eligibility.UNAVAILABLE,
            eligibility_reason="NYAIP assignment is not an agent-selected voluntary market; no official electronic filing.",
            status=RatingJob.Status.EXCLUDED,
            actor=self.user,
        )
        self.assertEqual(job.status, RatingJob.Status.EXCLUDED)
        self.assertIn("not an agent-selected", job.eligibility_reason)

    def test_quote_requires_parent(self):
        with self.assertRaises(ValueError):
            append_quote_version(
                organization=self.org,
                market=self.market,
                premium="100",
            )
