"""Tests for client mobile wallet API."""

from datetime import date
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import (
    Client,
    ClientAppSession,
    InsuranceCompany,
    InsurancePolicy,
    InsurancePolicyInstallment,
    Organization,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ClientAppAPITests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Wallet PSB",
            city="Buffalo",
            state="NY",
            portal_token="test-portal-token-abc",
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            first_name="Ada",
            last_name="Lovelace",
            phone_number="(555) 123-4567",
            email="ada@example.com",
            app_access_enabled=True,
        )
        self.client_obj.set_app_pin("1234")
        self.client_obj.save(update_fields=["app_pin_hash"])

        self.company = InsuranceCompany.objects.create(
            organization=self.org,
            name="Acme Ins",
        )
        self.policy = InsurancePolicy.objects.create(
            organization=self.org,
            client=self.client_obj,
            insurance_company=self.company,
            policy_number="POL-100",
            named_insured="Ada Lovelace",
            premium=Decimal("1200.00"),
            commission_rate=Decimal("15.00"),
            commission_amount=Decimal("180.00"),
            start_date=date(2026, 1, 1),
            end_date=date(2027, 1, 1),
            status=InsurancePolicy.StatusChoices.ACTIVE,
            stage=InsurancePolicy.StageChoices.BOUND,
        )
        InsurancePolicyInstallment.objects.create(
            policy=self.policy,
            installment_number=1,
            due_date=date(2026, 10, 1),
            amount=Decimal("100.00"),
            installment_fee=Decimal("0.00"),
            is_paid=False,
        )

        self.login_url = reverse("api-client-login")
        self.home_url = reverse("api-client-home")
        self.me_url = reverse("api-client-me")
        self.logout_url = reverse("api-client-logout")
        self.policies_url = reverse("api-client-policies")

    def _login(self, **overrides):
        payload = {
            "portal_token": "test-portal-token-abc",
            "phone": "5551234567",
            "pin": "1234",
        }
        payload.update(overrides)
        return self.client.post(self.login_url, payload, format="json")

    def test_login_returns_token(self):
        response = self._login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["client"]["first_name"], "Ada")
        self.assertTrue(ClientAppSession.objects.filter(token=response.data["token"]).exists())

    def test_login_with_email(self):
        response = self._login(phone="", email="ada@example.com")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_invalid_pin(self):
        response = self._login(pin="9999")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("PIN", response.data["detail"])

    def test_login_disabled_access(self):
        self.client_obj.app_access_enabled = False
        self.client_obj.save(update_fields=["app_access_enabled"])
        response = self._login()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("not enabled", response.data["detail"].lower())

    def test_home_requires_auth(self):
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_home_with_token(self):
        token = self._login().data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["client"]["id"], self.client_obj.id)
        self.assertGreaterEqual(response.data["totals"]["policies"], 1)
        self.assertIsNotNone(response.data["next_payment"])

    def test_policies_and_schedule(self):
        token = self._login().data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        policies = self.client.get(self.policies_url)
        self.assertEqual(policies.status_code, status.HTTP_200_OK)
        self.assertEqual(policies.data["count"], 1)

        detail = self.client.get(
            reverse("api-client-policy-detail", kwargs={"policy_id": self.policy.id})
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertIn("schedule", detail.data)

        schedule = self.client.get(
            reverse("api-client-policy-schedule", kwargs={"policy_id": self.policy.id})
        )
        self.assertEqual(schedule.status_code, status.HTTP_200_OK)
        self.assertEqual(schedule.data["remaining"], 1)

    def test_logout_revokes_session(self):
        token = self._login().data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session = ClientAppSession.objects.get(token=token)
        self.assertIsNotNone(session.revoked_at)
        me = self.client.get(self.me_url)
        self.assertEqual(me.status_code, status.HTTP_401_UNAUTHORIZED)
