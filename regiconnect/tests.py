from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import date

from core.models import Client, InsuranceCompany, InsurancePolicy, Organization, OrganizationMembership, Space, Vehicle
from core.role_permissions import apply_role_permission_pack
from core.insurance_quote_pipeline_models import InsuranceQuoteLead

from regiconnect.access import evaluate_market_access
from regiconnect.acord import map_canonical_to_acord
from regiconnect.appetite import evaluate_appetite
from regiconnect.catalog import ensure_builtin_connectors
from regiconnect.certification import approve_production, run_certification
from regiconnect.engines import create_submission, request_bind, submit_and_quote
from regiconnect.exceptions import MissingCarrierSpec, TerminalConnectorError
from regiconnect.models import (
    Appointment,
    CanonicalQuote,
    Connection,
    Connector,
    MarketProfile,
    ProducerCode,
    SecretReference,
    Submission,
)
from regiconnect.secrets import load_secret, store_secret
from regiconnect.sftp import assert_host_key_verified
from regiconnect.webhooks import verify_and_store
from core.models import DailyPaymentTransaction


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class RegiConnectTests(TestCase):
    def setUp(self):
        ensure_builtin_connectors()
        self.org = Organization.objects.create(name="Connect Org", city="NYC")
        self.other = Organization.objects.create(name="Other Org", city="NYC")
        self.owner_user = User.objects.create_user("rcowner", password="password123")
        self.owner = OrganizationMembership.objects.create(
            user=self.owner_user,
            organization=self.org,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        apply_role_permission_pack(self.owner)
        self.space = Space.objects.create(organization=self.org, key="insurance", label="Insurance")
        self.owner.accessible_spaces.add(self.space)
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Mock Mutual")
        self.insured = Client.objects.create(
            organization=self.org,
            first_name="Jane",
            last_name="Doe",
            phone_number="5551112222",
            state="NY",
        )
        self.market = MarketProfile.objects.create(
            organization=self.org,
            company=self.company,
            market_type=MarketProfile.MarketType.CARRIER,
            status=MarketProfile.Status.ACTIVE,
            states=["NY"],
            lines_of_business=["auto_personal"],
        )
        Appointment.objects.create(
            organization=self.org,
            market=self.market,
            state="NY",
            line_of_business="auto_personal",
            status=Appointment.Status.ACTIVE,
            effective_date=timezone.localdate(),
        )
        ProducerCode.objects.create(
            organization=self.org,
            market=self.market,
            code="P-99",
            state="NY",
            line_of_business="auto_personal",
        )
        self.car = Vehicle.objects.create(
            client=self.insured,
            vin="1HGCM82633A004352",
            year=2015,
            make="Honda",
            model="Accord",
        )
        self.connector = Connector.objects.get(slug="mock")
        self.connection = Connection.objects.create(
            organization=self.org,
            market=self.market,
            connector=self.connector,
            environment=Connection.Environment.SANDBOX,
            status=Connection.Status.ACTIVE,
            capabilities=self.connector.capabilities,
        )

    def test_tenant_isolation_on_submissions(self):
        sub = create_submission(
            organization=self.org,
            market=self.market,
            connection=self.connection,
            actor=self.owner_user,
            client=self.insured,
            state="NY",
            line_of_business="auto_personal",
        )
        self.assertFalse(Submission.objects.filter(organization=self.other).exists())
        self.assertEqual(Submission.objects.get(pk=sub.id).organization_id, self.org.id)

    def test_appointment_defaults_pending(self):
        pending = Appointment.objects.create(organization=self.org, market=self.market)
        self.assertEqual(pending.status, Appointment.Status.PENDING)

    def test_mock_quote_enters_existing_pipeline_then_bind_policy_and_finance(self):
        submission = create_submission(
            organization=self.org,
            market=self.market,
            connection=self.connection,
            actor=self.owner_user,
            client=self.insured,
            state="NY",
            line_of_business="auto_personal",
            extra={"idempotency_key": "e2e-1", "name": "Jane Doe"},
        )
        submit_and_quote(submission)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.Status.QUOTED)
        quote = CanonicalQuote.objects.get(submission=submission)
        lead = InsuranceQuoteLead.objects.get(organization=self.org)
        self.assertEqual(lead.stage, InsuranceQuoteLead.Stage.QUOTED)
        self.assertEqual(lead.regi_connectivity.quote_source, "regi_connect")
        self.assertEqual(lead.regi_connectivity.premium, quote.premium)
        bind = request_bind(quote, actor=self.owner_user)
        bind.refresh_from_db()
        self.assertEqual(bind.status, bind.Status.BOUND)
        policy = InsurancePolicy.objects.get(organization=self.org, policy_number__startswith="MOCK-POL")
        self.assertEqual(policy.stage, InsurancePolicy.StageChoices.BOUND)
        self.assertEqual(policy.regi_connectivity.external_policy_number, policy.policy_number)
        self.assertTrue(
            DailyPaymentTransaction.objects.filter(
                organization=self.org, insurance_policy=policy
            ).exists()
        )

    def test_submission_idempotency(self):
        a = create_submission(
            organization=self.org,
            market=self.market,
            connection=self.connection,
            actor=self.owner_user,
            client=self.insured,
            extra={"idempotency_key": "same"},
        )
        b = create_submission(
            organization=self.org,
            market=self.market,
            connection=self.connection,
            actor=self.owner_user,
            client=self.insured,
            extra={"idempotency_key": "same"},
        )
        self.assertEqual(a.id, b.id)

    def test_unspecified_connector_cannot_go_production(self):
        spec = Connector.objects.get(slug="unspecified")
        conn = Connection.objects.create(
            organization=self.org,
            market=self.market,
            connector=spec,
            environment=Connection.Environment.SANDBOX,
            status=Connection.Status.TESTING,
        )
        run = run_certification(conn)
        self.assertEqual(run.status, run.Status.FAILED)
        with self.assertRaises(TerminalConnectorError):
            approve_production(conn, self.owner_user)

    def test_secrets_round_trip_not_plaintext(self):
        row = store_secret(self.org, {"api_key": "super-secret"})
        self.assertNotIn("super-secret", row.payload_encrypted)
        self.assertEqual(load_secret(row.reference, self.org.id)["api_key"], "super-secret")
        self.assertFalse(SecretReference.objects.filter(payload_encrypted="super-secret").exists())

    def test_sftp_production_requires_host_key(self):
        from regiconnect.models import SftpEndpoint

        prod = Connection.objects.create(
            organization=self.org,
            market=self.market,
            connector=self.connector,
            environment=Connection.Environment.PRODUCTION,
            status=Connection.Status.ACTIVE,
            production_approved_at=timezone.now(),
        )
        endpoint = SftpEndpoint.objects.create(
            organization=self.org, connection=prod, host="sftp.example.com"
        )
        with self.assertRaises(TerminalConnectorError):
            assert_host_key_verified(endpoint)
        endpoint.host_key_fingerprint = "sha256:abc"
        endpoint.save()
        assert_host_key_verified(endpoint)

    def test_acord_stub_requires_mapping(self):
        with self.assertRaises(MissingCarrierSpec):
            map_canonical_to_acord(self.connector, "100", {"x": 1})

    def test_webhook_duplicate(self):
        body = b'{"event":"quoted","correlation_id":"c1"}'
        headers = {"X-RegiConnect-Event-Id": "evt-1"}
        first = verify_and_store(connection=self.connection, body=body, headers=headers)
        second = verify_and_store(connection=self.connection, body=body, headers=headers)
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.status, second.Status.DUPLICATE)

    def test_space_tabs_for_owner(self):
        self.client.login(username="rcowner", password="password123")
        url = reverse("inventory-detail", args=[self.space.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Markets &amp; Access")
        self.assertContains(response, "Connectivity")
        self.assertContains(response, "Submissions")
        self.assertContains(response, "not free access")

    def test_api_requires_membership_org(self):
        token_user = self.owner_user
        from rest_framework.authtoken.models import Token

        token, _ = Token.objects.get_or_create(user=token_user)
        url = reverse("regiconnect-api:api-dashboard")
        denied = self.client.get(url, HTTP_AUTHORIZATION=f"Token {token.key}", HTTP_X_ORGANIZATION_ID=str(self.other.id))
        self.assertEqual(denied.status_code, 403)
        ok = self.client.get(url, HTTP_AUTHORIZATION=f"Token {token.key}", HTTP_X_ORGANIZATION_ID=str(self.org.id))
        self.assertEqual(ok.status_code, 200)
        self.assertIn("stats", ok.json())

    def test_market_access_and_appetite(self):
        decision = evaluate_market_access(
            organization=self.org,
            market=self.market,
            state="NY",
            line_of_business="auto_personal",
        )
        self.assertTrue(decision.allowed)
        from regiconnect.models import AppetiteRule

        AppetiteRule.objects.create(
            organization=self.org,
            market=self.market,
            name="NY auto",
            criteria=[{"field": "state", "op": "in", "value": ["NY"]}],
            result_on_match="eligible",
        )
        appetite = evaluate_appetite(self.market, {"state": "NY"})
        self.assertEqual(appetite.result, "eligible")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_mock_submit_runs_inline_without_celery_worker(self):
        from unittest.mock import patch

        self.client.login(username="rcowner", password="password123")
        with patch("regiconnect.tasks.run_connector_job.delay") as delay:
            response = self.client.post(
                reverse("regiconnect:submit"),
                {
                    "organization": self.org.id,
                    "connection_id": self.connection.id,
                    "client_id": self.insured.id,
                    "vehicle_id": self.car.id,
                    "extra_driver_name": "Sam Doe",
                    "extra_driver_dl": "111222333",
                    "extra_vehicle_vin": "1FTFW1ET1EFA00001",
                    "extra_vehicle_year": "2018",
                    "extra_vehicle_make": "Ford",
                    "extra_vehicle_model": "F150",
                    "state": "NY",
                    "line_of_business": "auto_personal",
                },
            )
        delay.assert_not_called()
        self.assertEqual(response.status_code, 302)
        submission = Submission.objects.get(organization=self.org)
        self.assertEqual(submission.status, Submission.Status.QUOTED)
        quote = submission.quotes.get()
        self.assertEqual(str(quote.premium), "1200.00")
        self.assertEqual(submission.canonical_payload["additional_drivers"][0]["name"], "Sam Doe")
        self.assertEqual(submission.canonical_payload["additional_vehicles"][0]["vin"], "1FTFW1ET1EFA00001")

    def test_mock_bundle_activates_existing_pending_rows(self):
        Appointment.objects.filter(organization=self.org).update(status=Appointment.Status.PENDING)
        self.connection.status = Connection.Status.PENDING
        self.connection.save(update_fields=["status"])
        self.client.login(username="rcowner", password="password123")
        response = self.client.post(
            reverse("regiconnect:mock-bundle"),
            {"organization": self.org.id, "company_id": self.company.id},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("tab=regi-markets", response["Location"])
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, Connection.Status.ACTIVE)
        self.assertTrue(
            Appointment.objects.filter(
                organization=self.org, market=self.market, status=Appointment.Status.ACTIVE
            ).exists()
        )

    def test_canonical_payload_includes_driver_and_vehicle(self):
        self.insured.driver_license = "123456789"
        self.insured.dob = date(1990, 5, 5)
        self.insured.save(update_fields=["driver_license", "dob"])
        car = Vehicle.objects.create(
            client=self.insured,
            vin="1FTFW1ET1EFA00001",
            year=2023,
            make="Ford",
            model="F150",
        )
        submission = create_submission(
            organization=self.org,
            market=self.market,
            connection=self.connection,
            actor=self.owner_user,
            client=self.insured,
            vehicle=car,
            extra={
                "idempotency_key": "payload-1",
                "coverage_type": "full",
                "has_accident": True,
                "additional_drivers": [{"name": "Sam Doe", "driver_license": "111", "dob": "2000-01-01"}],
                "additional_vehicles": [{"vin": "1HGCM82633A004352", "year": "2018", "make": "Honda", "model": "Civic"}],
            },
        )
        payload = submission.canonical_payload
        self.assertEqual(payload["vehicle"]["vin"], "1FTFW1ET1EFA00001")
        self.assertEqual(payload["driver"]["driver_license"], "123456789")
        self.assertEqual(payload["coverage"]["type"], "full")
        self.assertEqual(payload["additional_drivers"][0]["name"], "Sam Doe")
        self.assertEqual(payload["additional_vehicles"][0]["make"], "Honda")
        submit_and_quote(submission)
        quote = submission.quotes.get()
        self.assertEqual(str(quote.premium), "1850.00")
        self.assertEqual(quote.coverage.get("vin"), "1FTFW1ET1EFA00001")

    def test_capture_client_and_vehicle_from_extracted_fields(self):
        self.client.login(username="rcowner", password="password123")
        created = self.client.post(
            reverse("regiconnect:capture-client"),
            {
                "organization": self.org.id,
                "first_name": "Omar",
                "last_name": "Ali",
                "driver_license": "987654321",
                "dob": "1991-05-05",
                "state": "NY",
                "city": "Bronx",
            },
        )
        self.assertEqual(created.status_code, 200)
        body = created.json()
        self.assertTrue(body["ok"])
        client = Client.objects.get(id=body["client_id"])
        self.assertEqual(client.driver_license, "987654321")
        vehicle_resp = self.client.post(
            reverse("regiconnect:capture-vehicle"),
            {
                "organization": self.org.id,
                "client_id": client.id,
                "vin": "1HGCM82633A004352",
                "year": "2018",
                "make": "Honda",
                "model": "Civic",
            },
        )
        self.assertEqual(vehicle_resp.status_code, 200)
        self.assertTrue(vehicle_resp.json()["ok"])
        denied = self.client.post(
            reverse("regiconnect:capture-vehicle"),
            {
                "organization": self.org.id,
                "client_id": Client.objects.create(
                    organization=self.other, first_name="Other", last_name="Person"
                ).id,
                "vin": "1HGCM82633A004352",
            },
        )
        self.assertEqual(denied.status_code, 404)
